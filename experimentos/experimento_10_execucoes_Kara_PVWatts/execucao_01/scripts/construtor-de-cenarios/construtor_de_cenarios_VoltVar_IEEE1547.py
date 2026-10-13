#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
O script gera diferentes cenários de penetração de PV, a partir dos loadshapes
declarados na simulação de base (sem PV).

A potência total de geração PV inserida na é determinada por uma lista
contendo os percentuais em forma decimal. Ex.: [0.2, 0.3, 0.4]

A potência individual de cada geração PV é determinada por uma lista de valores
possíveis. A seleção pode ocorrer de maneira aleatória, mas podem também ser fornecida
uma lista de pesos, aumentando a probabilidade de seleção de uma potência PV específica.

A potência PV instalada em cada bus é limitada a um percentual máximo da potência do bus,
para evitar concentrações excessivas de geração.

O processo consiste nas seguintes etapas:
    
    1. Leitura do baseload e calculo da carga média diurna no barramento da
    subestação.Leitura da curva de potência ativa do barramento da subestação, sem PV.
    
    2. Determina a potência PV total (Potência alvo) a ser inserida;
    
    3. Leitura dos arquivos Loadshapes.dss para coletar
    dados dos bus (identificador e carga).
    
    4. Realiza a inserção dos PVs
         4.1 - Gera uma população de PVs com base em uma lista de potências individuais
               possíveis de serem atribuídas aos PVs
               Permite incluir uma lista de pesos, os quais determinam a probabilidade de ocorrência
               de uma determinada potência PV. Se for desejado que todos as potências da lista
               tenham a mesma possibilidade de ocorrência, os pesos devem ser todos iguais a 1

         4.2 - Ordena a população PV em ordem decrescente de potência
         
         4.3 - Distribuia a população PV entre os buses
               respeitando o limite máximo de penetração PV.
               
         4.4 - Gera relatório

    5. Constroi os arquivos 'geradoresPV_XX.dss' contendo os geradores PV distribuidos.
         5.1 - Verifica o número de bases do bus para a correta parametrização do PV
        
         5.2 - Cria os arquivo .dss contendo a definição de todos os PVs do cenário de analisado.
         O PV é inserido na rede através do comando "New PVSystem" com seus respectivos parâmetros:
         nome, bus de conexão, número de fases, potência e loadshapes de irradiância e temperatura.
        
         5.3 - Gera o arquivo Master.dss com o "Redirect" para o arquivo de .dss que contém
         os PVSystems do cenário simulado.
        
         5.4 - Funções para plotagens
        
    6. Outras plotagens. Plota curvas baseload (carga média diurna) e níveis PV 

    
ENTRADAS:
    + Lista contendo os percentuais de penetração PV desejado
    + Resultados da simulação base {resultados_sem_PV.parquet}
    + Arquivos Loadshapes.dss {Loadshapes_FeederA,
                               Loadshapes_FeederB,
                               Loadshapes_FeederC}
    
SAÍDAS:
    + Para cada cenário:
        geradoresPV_XX.dss
        geradoresPV_XX_VV.dss
        geradoresPV_XX.xlsx
        PV_MasterXX.dss
        PV_MasterXX_VV.dss
        (XX é o nível de penetração)
        
    + Relatório de processamento log_contrucao_cenarios.txt

"""

import sys
import random
import re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg


############################################################
##########  DECLARAÇÃO DE FUNÇÕES ##########################

# Etapa 1 - Leitura do baseload e calculo da carga
# média diurna no barramento da subestação.
def calcula_media_diurna(
        caminho_parquet_baseload # caminho para o arquivo parquet que
        ):                       # contém os resultados da simulação sem PV

    df = pd.read_parquet(caminho_parquet_baseload)
    
    # Verifica se existe a coluna P_kW
    if "P_kW" not in df.columns:
        print("Coluna P_kW não encontrada.")

    # Desconsidera o sinal +/-
    df["P_kW"] = (df["P_kW"].abs())

    # Para cada hora, calcula a carga média
    curva_media = (df.groupby("hora")["P_kW"].mean())

    # Seleciona apenas as médias entre 6 e 18 horas
    curva_media = curva_media[
        (curva_media.index >= 6)
        &
        (curva_media.index <= 18)
    ]

    # Calcula a curva média no período considerado
    carga_media = curva_media.mean()

    print(
        f"\nCarga média diurna sem PV = "
        f"{carga_media:.2f} kW"
    )

    return (carga_media, curva_media)

# Etapa 2 - Determina a potência PV total (Potência alvo) a ser inserida
def salvar_potencias_cenarios(percentuais, potencias):
    """
    Salva em Excel as potências-alvo correspondentes aos níveis de
    penetração PV calculados na Etapa 2.

    Formato compatível com o estimador:
        cenario | potencia_PV_kW
    """
    dados = []
    for percentual, potencia in zip(percentuais, potencias):
        dados.append({
            "cenario": int(round(100.0 * percentual)),
            "potencia_PV_kW": round(float(potencia), 3)
        })

    df = pd.DataFrame(dados)

    # Mantém o nome já utilizado pelo projeto.
    arquivo = cfg.COM_PV / "Potencias_Cenarios.xlsx"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(arquivo, index=False)

    print("\nSalvando potências dos cenários")
    print(f"Arquivo salvo: {arquivo.name}")


def calcula_potencia_PV_alvo(
        carga_media,  # carga média diurna
        penetracao_PV # percentual de penetração PV desejado, forma decimal.
        ):

    alvos_PV = []

    for p in penetracao_PV:

        geracaoPV = carga_media * p

        alvos_PV.append(geracaoPV)

    return alvos_PV

# Etapa 3 - Leitura das cargas e caracterização por feeder/fases
#
# Os três feeders são lidos separadamente, mas os loads são reunidos em uma
# estrutura única contendo feeder, fases, conexão e potência.
#
# A distribuição dos PVs é feita de forma ponderada entre feeders e fases:
#   - quantidade de loads de cada feeder;
#   - quantidade de loads mono/bi/tri em cada feeder;
#   - PVs de 10/15/20 kW somente em loads trifásicos;
#   - PVs de 3/5/8 kW podem ser mono, bi ou trifásicos;
#   - limite de potência PV por bus.
#
# O objetivo é evitar que a realização aleatória concentre PVs excessivamente
# em um único feeder ou em uma única classe de fases.

def _normalizar_bus(bus):
    """
    Retorna o nome-base do barramento, removendo a lista de fases.

    Ex.:
        t_bus3103_l.1.2       -> t_bus3103_l
        t_bus3072_l.1.2.3.0  -> t_bus3072_l
        t_bus3103_l           -> t_bus3103_l

    A correspondência entre LoadShape e Load é feita por esse nome-base,
    pois a declaração das fases pode aparecer apenas no arquivo Load.
    """
    if bus is None:
        return None
    bus = str(bus).strip().strip('"\'').lower()
    return bus.split('.')[0]


def _extrair_parametro_dss(linha, parametro):
    match = re.search(
        rf"\b{parametro}\s*=\s*([^\s]+)",
        linha,
        flags=re.IGNORECASE
    )
    return match.group(1).rstrip(',') if match else None


def _ler_cadastro_cargas(caminho_loads):
    """
    Lê os arquivos Loads_FeederA/B/C e cadastra cada carga por seu
    barramento-base, preservando phases, conn e feeder de origem.
    """
    cadastro = {}

    for arquivo in caminho_loads:
        nome_arquivo = Path(arquivo).name.lower()
        if 'feeder a' in nome_arquivo or 'feeder_a' in nome_arquivo or 'feedera' in nome_arquivo:
            feeder = 'A'
        elif 'feeder b' in nome_arquivo or 'feeder_b' in nome_arquivo or 'feederb' in nome_arquivo:
            feeder = 'B'
        elif 'feeder c' in nome_arquivo or 'feeder_c' in nome_arquivo or 'feederc' in nome_arquivo:
            feeder = 'C'
        else:
            feeder = None

        with open(arquivo, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith('!'):
                    continue

                bus = _extrair_parametro_dss(linha, 'bus1')
                phases = _extrair_parametro_dss(linha, 'phases')
                conn = _extrair_parametro_dss(linha, 'conn')

                if bus is None or phases is None:
                    continue

                try:
                    phases = int(float(phases))
                except (ValueError, TypeError):
                    continue

                chave = _normalizar_bus(bus)
                cadastro[chave] = {
                    'bus_original': bus,
                    'phases': phases,
                    'conn': conn.lower() if conn else 'wye',
                    'feeder': feeder
                }

    return cadastro


def buscar_dados_buses(caminho_loadshapes, caminho_loads):
    """
    Associa cada LoadShape à carga original pelo barramento-base.

    O feeder é determinado pelo arquivo de origem (FeederA/B/C), e não
    pelo nome do bus. Assim a caracterização dos três feeders permanece
    independente da convenção de nomenclatura dos barramentos.
    """
    cadastro = _ler_cadastro_cargas(caminho_loads)
    dados_buses = []
    nao_encontrados = []

    for loadshape in caminho_loadshapes:
        nome_ls = Path(loadshape).name.lower()
        if 'feeder a' in nome_ls or 'feeder_a' in nome_ls or 'feedera' in nome_ls:
            feeder_ls = 'A'
        elif 'feeder b' in nome_ls or 'feeder_b' in nome_ls or 'feederb' in nome_ls:
            feeder_ls = 'B'
        elif 'feeder c' in nome_ls or 'feeder_c' in nome_ls or 'feederc' in nome_ls:
            feeder_ls = 'C'
        else:
            feeder_ls = None

        with open(loadshape, 'r', encoding='utf-8') as f:
            for linha in f:
                linha_lower = linha.lower()
                if 'bus1=' not in linha_lower or 'kw=' not in linha_lower:
                    continue

                bus = _extrair_parametro_dss(linha, 'bus1')
                kw_txt = _extrair_parametro_dss(linha, 'kw')
                if bus is None or kw_txt is None:
                    continue

                try:
                    kw = abs(float(kw_txt))
                except (ValueError, TypeError):
                    continue

                chave = _normalizar_bus(bus)
                carga = cadastro.get(chave)

                if carga is None:
                    nao_encontrados.append((feeder_ls, bus))
                    continue

                # O feeder vem do arquivo LoadShape. Como verificação,
                # também conferimos o feeder cadastrado no arquivo Load.
                feeder = feeder_ls or carga['feeder']
                if carga['feeder'] is not None and feeder_ls is not None and carga['feeder'] != feeder_ls:
                    print(
                        f"AVISO: feeder inconsistente para bus={bus}: "
                        f"Load={carga['feeder']} / LoadShape={feeder_ls}. "
                        f"Será usado o feeder do LoadShape."
                    )

                dados_buses.append({
                    'bus': bus,
                    'kw': kw,
                    'phases': carga['phases'],
                    'conn': carga['conn'],
                    'feeder': feeder
                })

    if not dados_buses:
        raise RuntimeError(
            'Nenhum load elegível foi encontrado. '
            'Verifique a correspondência entre Loads_FeederA/B/C.dss e Loadshapes_FeederA/B/C.dss.'
        )

    # IMPORTANTE: um barramento físico pode aparecer em mais de um registro
    # de LoadShape. Para o limite de inserção de PV, a carga deve ser tratada
    # como a carga TOTAL daquele barramento, e não como registros separados.
    # Caso contrário, o algoritmo poderia criar dois estados independentes
    # para o mesmo bus e, somando os PVs, ultrapassar o limite físico definido.
    dados_agregados = {}
    for item in dados_buses:
        chave = (item['feeder'], _normalizar_bus(item['bus']))

        if chave not in dados_agregados:
            dados_agregados[chave] = {
                'bus': _normalizar_bus(item['bus']),
                'kw': 0.0,
                'phases': item['phases'],
                'conn': item['conn'],
                'feeder': item['feeder']
            }
        else:
            # Se houver registros repetidos do mesmo bus, soma a carga.
            # A fase deve ser consistente; se não for, interrompe para evitar
            # criar um PV com uma configuração elétrica ambígua.
            if dados_agregados[chave]['phases'] != item['phases']:
                raise ValueError(
                    f"Fases inconsistentes para o mesmo bus {item['bus']}: "
                    f"encontrado {dados_agregados[chave]['phases']} e "
                    f"{item['phases']} fases."
                )

        dados_agregados[chave]['kw'] += item['kw']

    dados_buses = list(dados_agregados.values())

    print(f"\nRegistros de LoadShape encontrados: {len(dados_buses)} buses físicos elegíveis após agregação")

    if nao_encontrados:
        print(
            f"AVISO: {len(nao_encontrados)} registros de LoadShape não encontraram "
            f"carga correspondente pelo barramento-base."
        )
        for feeder, bus in nao_encontrados[:10]:
            print(f"  Não encontrado: feeder={feeder}, bus={bus}")
        if len(nao_encontrados) > 10:
            print(f"  ... e mais {len(nao_encontrados)-10} registros.")

    print('\nCARACTERIZAÇÃO DOS FEEDERS:')
    for feeder in ('A', 'B', 'C'):
        subset = [x for x in dados_buses if x['feeder'] == feeder]
        n1 = sum(x['phases'] == 1 for x in subset)
        n2 = sum(x['phases'] == 2 for x in subset)
        n3 = sum(x['phases'] == 3 for x in subset)
        carga_total = sum(x['kw'] for x in subset)
        print(
            f"  Feeder {feeder}: {len(subset)} loads | "
            f"{carga_total:.2f} kW | mono={n1} | bi={n2} | tri={n3}"
        )

    return dados_buses



# ================================================================
# POTENCIAS DOS PVs
# 3, 5 e 8 kW: podem ser mono, bi ou trifásicos.
# 10, 15 e 20 kW: obrigatoriamente trifásicos.
# ================================================================
POTENCIAS_PV_NAO_TRIFASICAS = [3.0, 5.0, 8.0]
POTENCIAS_PV_TRIFASICAS = [10.0, 15.0, 20.0]
POTENCIAS_PV = (
    POTENCIAS_PV_NAO_TRIFASICAS
    + POTENCIAS_PV_TRIFASICAS
)

def _fase_compativel(pv, bus):
    if pv["potencia"] in POTENCIAS_PV_TRIFASICAS:
        return bus["phases"] == 3

    return bus["phases"] in (1, 2, 3)


def _estatisticas_feeders(estado_buses):
    stats = {}

    for feeder in ("A", "B", "C"):
        subset = [
            x for x in estado_buses
            if x["feeder"] == feeder
        ]

        stats[feeder] = {
            "loads": len(subset),
            "pvs": sum(x["numero_pvs"] for x in subset),
            "pv_kw": sum(x["pv_instalado"] for x in subset),
            "pv_por_fase": {
                1: sum(
                    x["numero_pvs"]
                    for x in subset
                    if x["phases"] == 1
                ),
                2: sum(
                    x["numero_pvs"]
                    for x in subset
                    if x["phases"] == 2
                ),
                3: sum(
                    x["numero_pvs"]
                    for x in subset
                    if x["phases"] == 3
                )
            }
        }

    return stats


def _maior_resto_alocacao(valores, total):
    """Distribui um total inteiro proporcionalmente aos valores.

    Usa o método do maior resto para que a soma das quotas seja exatamente
    igual a ``total``.
    """
    chaves = list(valores.keys())
    if total <= 0 or not chaves:
        return {k: 0 for k in chaves}

    soma = sum(max(0.0, float(valores[k])) for k in chaves)
    if soma <= 0:
        base = {k: 0 for k in chaves}
        for k in chaves[:total]:
            base[k] += 1
        return base

    quotas = {k: total * max(0.0, float(valores[k])) / soma for k in chaves}
    inteiros = {k: int(quotas[k]) for k in chaves}
    faltam = total - sum(inteiros.values())

    ordem = sorted(
        chaves,
        key=lambda k: quotas[k] - inteiros[k],
        reverse=True
    )

    for k in ordem[:faltam]:
        inteiros[k] += 1

    return inteiros


def _quotas_feeders(estado_buses, n_pvs):
    """Calcula quotas determinísticas de PVs por feeder.

    A quota combina, em partes iguais:
      - proporção do número de loads;
      - proporção da potência ativa instalada nos loads.

    A combinação evita que a distribuição seja dominada apenas pelo número
    de consumidores ou apenas pela potência, mantendo os três feeders
    representados de acordo com sua dimensão real.
    """
    feeders = ("A", "B", "C")
    cargas = {}
    potencias = {}

    for feeder in feeders:
        subset = [x for x in estado_buses if x["feeder"] == feeder]
        cargas[feeder] = len(subset)
        potencias[feeder] = sum(x["kw"] for x in subset)

    total_cargas = sum(cargas.values())
    total_potencias = sum(potencias.values())

    pesos = {}
    for feeder in feeders:
        p_cargas = cargas[feeder] / total_cargas if total_cargas else 0.0
        p_pot = potencias[feeder] / total_potencias if total_potencias else 0.0
        pesos[feeder] = 0.50 * p_cargas + 0.50 * p_pot

    quotas = _maior_resto_alocacao(pesos, n_pvs)

    print("\nQUOTAS DE PVs POR FEEDER:")
    for feeder in feeders:
        print(
            f"  Feeder {feeder}: {quotas[feeder]} PVs "
            f"(peso={100*pesos[feeder]:.2f}%)"
        )

    return quotas


def _capacidade_disponivel(bus, max_pot_PV=0.40):
    """Retorna a potência PV ainda disponível no bus."""
    limite = max_pot_PV * bus["kw"]
    return max(0.0, limite - bus["pv_instalado"])


def _pontuacao_bus(bus, potencia, proporcao_fase, proporcao_feeder,
                   pv_por_feeder, max_pot_PV=0.40):
    """Calcula o peso de escolha de um bus elegível.

    A pontuação favorece:
      - feeders que ainda estão abaixo da quota de PVs;
      - fases cuja presença é compatível com a composição das cargas;
      - buses com maior capacidade disponível;
      - menor penetração acumulada no bus.

    Não é uma quota rígida de fases: é uma preferência. Assim, a população
    de PVs pode ser totalmente alocada quando a capacidade física exigir uma
    composição mono/bi/tri diferente da composição dos loads.
    """
    capacidade = _capacidade_disponivel(bus, max_pot_PV)
    if capacidade <= 0:
        return 0.0

    penetracao = (
        bus["pv_instalado"] / bus["kw"]
        if bus["kw"] > 0 else 1.0
    )

    peso_capacidade = max(0.05, capacidade)
    peso_penetracao = max(0.05, 1.0 - penetracao)
    peso_fase = max(0.05, proporcao_fase.get(bus["phases"], 0.05))
    peso_feeder = max(0.05, proporcao_feeder.get(bus["feeder"], 0.05))

    # Potência maior recebe uma preferência adicional por buses com maior
    # capacidade disponível. Isso reduz a chance de gastar cedo a capacidade
    # de buses que seriam os únicos capazes de receber 15/20 kW.
    folga_relativa = capacidade / max(1.0, bus["kw"])

    return (
        peso_capacidade
        * peso_penetracao
        * peso_fase
        * peso_feeder
        * max(0.10, folga_relativa)
    )


def distribuir_PVs(dados_bus, populacao_PV, max_pot_PV=0.40):
    """Distribui os PVs considerando simultaneamente feeder, fase e capacidade.

    Estratégia:
      1. As quotas de feeder são calculadas pela combinação 50% quantidade
         de loads + 50% potência dos loads.
      2. Não existe mais quota rígida de mono/bi/tri. A composição das cargas
         vira uma preferência estatística, porque a potência do PV impõe
         restrições físicas: 10/15/20 kW só podem ser trifásicos.
      3. PVs maiores são alocados primeiro. Isso evita que buses trifásicos
         capazes de receber 15/20 kW sejam ocupados prematuramente por PVs
         pequenos.
      4. Dentro dos feeders, a escolha dos buses permanece aleatória,
         ponderada pela capacidade, penetração e composição das cargas.
      5. Se um feeder atingir sua quota, um PV ainda não alocado pode usar
         outro feeder com capacidade física disponível. Isso mantém a
         potência solicitada sempre que houver capacidade global, em vez de
         simplesmente descartar PVs.
    """
    estado_buses = []
    for bus in dados_bus:
        estado_buses.append({
            "bus": bus["bus"],
            "kw": bus["kw"],
            "phases": bus["phases"],
            "conn": bus["conn"],
            "feeder": bus["feeder"],
            "pv_instalado": 0.0,
            "numero_pvs": 0
        })

    distribuicao = []
    n_pvs = len(populacao_PV)
    quotas_feeders = _quotas_feeders(estado_buses, n_pvs)

    feeders = ("A", "B", "C")
    contagem_fases = {}
    proporcao_fase = {}
    for feeder in feeders:
        subset = [x for x in estado_buses if x["feeder"] == feeder]
        contagem_fases[feeder] = {
            1: sum(x["phases"] == 1 for x in subset),
            2: sum(x["phases"] == 2 for x in subset),
            3: sum(x["phases"] == 3 for x in subset),
        }
        total = sum(contagem_fases[feeder].values())
        proporcao_fase[feeder] = {
            f: contagem_fases[feeder][f] / total if total else 0.0
            for f in (1, 2, 3)
        }

    proporcao_feeder = {
        f: quotas_feeders[f] / n_pvs if n_pvs else 0.0
        for f in feeders
    }

    print("\nPREFERÊNCIA DE FASES POR FEEDER:")
    for feeder in feeders:
        p = proporcao_fase[feeder]
        c = contagem_fases[feeder]
        print(
            f"  Feeder {feeder}: "
            f"mono={100*p[1]:.1f}% | bi={100*p[2]:.1f}% | "
            f"tri={100*p[3]:.1f}% "
            f"(loads: mono={c[1]} | bi={c[2]} | tri={c[3]})"
        )

    # PVs maiores primeiro. A população original continua aleatória, mas a
    # ordem de alocação protege a capacidade necessária para os PVs grandes.
    pvs = sorted(
        populacao_PV,
        key=lambda pv: pv["potencia"],
        reverse=True
    )

    # Estado de quantos PVs cada feeder já recebeu.
    pvs_por_feeder = {f: 0 for f in feeders}

    for pv in pvs:
        potencia = pv["potencia"]
        obrigatoriamente_tri = potencia in POTENCIAS_PV_TRIFASICAS

        candidatos = []
        pesos = []

        for bus in estado_buses:
            if not _fase_compativel(pv, bus):
                continue
            if obrigatoriamente_tri and bus["phases"] != 3:
                continue
            if _capacidade_disponivel(bus, max_pot_PV) + 1e-9 < potencia:
                continue

            feeder = bus["feeder"]
            quota = quotas_feeders[feeder]
            atual = pvs_por_feeder[feeder]

            # Forte preferência por feeders ainda abaixo da quota. Quando
            # todos os candidatos abaixo da quota forem inviáveis, o PV pode
            # usar outro feeder, preservando a potência total.
            deficit = max(0, quota - atual)
            if deficit > 0:
                fator_quota = 10.0 + deficit
            else:
                fator_quota = 0.20

            peso_bus = _pontuacao_bus(
                bus,
                potencia,
                proporcao_fase[feeder],
                proporcao_feeder,
                pvs_por_feeder,
                max_pot_PV
            )

            candidatos.append(bus)
            pesos.append(max(1e-9, fator_quota * peso_bus))

        if not candidatos:
            print(
                f"AVISO: não foi possível alocar {pv['nome']} "
                f"({potencia:.1f} kW) em nenhum bus elegível."
            )
            continue

        # Primeiro tenta obedecer às quotas de feeder. Se houver candidatos
        # apenas fora delas, a ponderação acima permite a redistribuição.
        bus = random.choices(candidatos, weights=pesos, k=1)[0]

        feeder = bus["feeder"]
        quota = quotas_feeders[feeder]
        if pvs_por_feeder[feeder] >= quota:
            print(
                f"AVISO: quota do Feeder {feeder} já atingida; "
                f"{pv['nome']} ({potencia:.1f} kW) será alocado por capacidade."
            )

        # Se a escolha saiu de um feeder cuja quota já estava cheia, o aviso
        # é informativo; não é erro físico.
        bus["pv_instalado"] += potencia
        bus["numero_pvs"] += 1
        pvs_por_feeder[feeder] += 1

        distribuicao.append({
            "nome": pv["nome"],
            "bus": bus["bus"],
            "phases": bus["phases"],
            "conn": bus["conn"],
            "feeder": feeder,
            "potencia": potencia
        })

    # Verificação final OBRIGATÓRIA do limite por barramento.
    # Não basta verificar cada alocação isoladamente: o limite é sobre a
    # potência PV acumulada no mesmo barramento físico.
    violacoes = []
    for bus in estado_buses:
        limite = max_pot_PV * bus["kw"]
        if bus["pv_instalado"] > limite + 1e-9:
            violacoes.append({
                "bus": bus["bus"],
                "carga": bus["kw"],
                "pv": bus["pv_instalado"],
                "limite": limite
            })

    if violacoes:
        detalhes = "\n".join(
            f"  {v['bus']}: carga={v['carga']:.3f} kW | "
            f"PV={v['pv']:.3f} kW | limite={v['limite']:.3f} kW"
            for v in violacoes
        )
        raise RuntimeError(
            "ERRO CRÍTICO: o cenário ultrapassou o limite máximo de "
            f"{100 * max_pot_PV:.1f}% de PV por barramento.\n"
            "O cenário NÃO será aceito. Barramentos violados:\n" + detalhes
        )

    print(
        f"\nVALIDAÇÃO FINAL PV/LOAD: OK — nenhum barramento ultrapassa "
        f"{100 * max_pot_PV:.1f}% de PV acumulado."
    )

    potencia_solicitada = sum(pv["potencia"] for pv in populacao_PV)
    potencia_distribuida = sum(pv["potencia"] for pv in distribuicao)

    if potencia_distribuida < potencia_solicitada:
        print("\nATENÇÃO: nem toda a potência da população PV foi alocada.")
        print(f"  Solicitada : {potencia_solicitada:.2f} kW")
        print(f"  Distribuída: {potencia_distribuida:.2f} kW")
    else:
        print("\nCAPACIDADE DE ALOCAÇÃO: OK")
        print(f"  Solicitada : {potencia_solicitada:.2f} kW")
        print(f"  Distribuída: {potencia_distribuida:.2f} kW")

    print("\nDISTRIBUIÇÃO FINAL POR FEEDER:")
    stats = _estatisticas_feeders(estado_buses)
    for feeder in feeders:
        s = stats[feeder]
        print(
            f"  Feeder {feeder}: {s['pvs']} PVs | "
            f"{s['pv_kw']:.2f} kW | "
            f"mono={s['pv_por_fase'][1]} | "
            f"bi={s['pv_por_fase'][2]} | "
            f"tri={s['pv_por_fase'][3]}"
        )

    return distribuicao, estado_buses


def gera_relatorio_PVs(estado_buses):
    resumo = []

    for bus in estado_buses:
        if bus["kw"] > 0:
            penetracao = (
                100 *
                bus["pv_instalado"] /
                bus["kw"]
            )
        else:
            penetracao = 0

        resumo.append({
            "bus": bus["bus"],
            "Feeder": bus["feeder"],
            "Fases": bus["phases"],
            "Conn": bus["conn"],
            "Carga_kW": bus["kw"],
            "PV_kW": round(bus["pv_instalado"], 2),
            "Penetracao": round(penetracao, 2),
            "Numero_PVs": bus["numero_pvs"]
        })

    return pd.DataFrame(resumo)


def gera_populacao_PVs(potencia_alvo, tolerancia=5.0):
    """Gera uma população aleatória de PVs próxima da potência alvo."""
    populacao_PV = []
    potencia_total = 0.0
    contador = 1

    while True:
        restante = potencia_alvo - potencia_total
        if abs(restante) <= tolerancia:
            break

        candidatos = [
            p for p in POTENCIAS_PV
            if potencia_total + p <= potencia_alvo + tolerancia
        ]
        if not candidatos:
            break

        # Quando estamos próximos do alvo, escolhe preferencialmente
        # a potência que deixa o menor erro residual.
        if restante <= max(POTENCIAS_PV):
            erro_min = min(abs(restante - p) for p in candidatos)
            candidatos = [
                p for p in candidatos
                if abs(abs(restante - p) - erro_min) < 1e-9
            ]

        potencia = random.choice(candidatos)
        populacao_PV.append({
            "nome": f"PV_{contador}",
            "potencia": float(potencia)
        })
        potencia_total += potencia
        contador += 1

    percentual = (100 * potencia_total / potencia_alvo) if potencia_alvo else 0.0
    print(f"Potência alvo       : {potencia_alvo:.2f} kW")
    print(f"Potência inserida    : {potencia_total:.2f} kW ({percentual:.2f}%)")
    print(f"Quantidade de PVs   : {len(populacao_PV)}")
    return populacao_PV


def ordenar_populacao_PVs(populacao):
    """Ordena os PVs da maior para a menor potência."""
    populacao.sort(key=lambda pv: pv["potencia"], reverse=True)
    return populacao


def GERA_POPULACAO_PVs(
        dados_bus,
        niveis_PV,
        potencias_PV
        ):

    cenarios = {}

    for nivel, potencia in zip(niveis_PV, potencias_PV):

        print(
            f"\nCENÁRIO COM {nivel*100:.2f} % DE PENETRAÇÃO"
        )

        populacao = gera_populacao_PVs(potencia)

        populacao = ordenar_populacao_PVs(populacao)

        distribuicao, estado_buses = distribuir_PVs(
            dados_bus,
            populacao,
            max_pot_PV=0.40
        )

        resumo = gera_relatorio_PVs(estado_buses)

        cenarios[potencia] = {
            "distribuicao": distribuicao,
            "resumo": resumo
        }

    return cenarios


# Etapa 5 - Constroi os arquivos .dss
# 5.1 - Verifica o número de fases do bus para a correta parametrização do PV
def extrai_num_fases(bus):

    partes = bus.split(".")

    if len(partes) == 1:
        return 3
    fases = [
        x
        for x in partes[1:]
        if x in ["1","2","3"]
    ]

    if len(fases) == 0:
        return 3

    return len(fases)

# 5.2 - Cria os arquivo .dss contendo a definição de todos os PVs do cenário de analisado.
# O PV é inserido na rede através do comando "New PVSystem" com seus respectivos parâmetros:
# nome, bus de conexão, número de fases, potência e loadshapes de irradiância e temperatura.
def geradoresPVs_dss(
        cenario,
        resumo,
        penetracaoPV,
        volt_var=False
        ):
    """
    Gera o arquivo DSS do cenário.

    3/5/8 kW -> fases conforme o load original.
    10/15/20 kW -> obrigatoriamente trifásicos.

    O cenário Volt-VAr usa exatamente os mesmos PVs e barramentos do cenário
    FP=1; apenas acrescenta a curva IEEE 1547 e o InvControl.
    """

    sufixo = "_VV" if volt_var else ""

    arquivo_dss = (
        cfg.COM_PV /
        f"geradoresPV_{int(100 * penetracaoPV)}{sufixo}.dss"
    )

    linhas = []

    for pv in cenario:
        fases = int(pv["phases"])
        potencia = float(pv["potencia"])

        if (
            potencia in POTENCIAS_PV_TRIFASICAS
            and fases != 3
        ):
            raise ValueError(
                f"{pv['nome']} de {potencia} kW foi alocado em "
                f"bus de {fases} fases. "
                f"PV de {potencia} kW deve ser trifásico."
            )

        linha = (
            f"New PVSystem.{pv['nome']} "
            f"bus1={pv['bus']} "
            f"phases={fases} "
            f"kV=0.208 "
            f"kVA={potencia:.3f} "
            f"Pmpp={potencia:.3f} "
            f"model=1 "
            f"conn=wye "
            f"pf=1 "
            f"irradiance=1 "
            f"temperature=25 "
            f"daily=PVShape"
        )

        linhas.append(linha)

    if volt_var:
        linhas.append("")
        linhas.append(
            "! Curva Volt-VAr IEEE 1547 utilizada no projeto"
        )
        linhas.append(
            "New XYCurve.VoltVarCurve "
            "npts=4 "
            "Xarray=[0.92 0.98 1.02 1.08] "
            "Yarray=[+0.44 0.00 0.00 -0.44]"
        )
        linhas.append(
            "New InvControl.InvPVCtrl "
            "mode=VOLTVAR "
            "vvc_curve1=VoltVarCurve "
            "voltage_curvex_ref=rated "
            "RefReactivePower=VARMAX "
            "deltaQ_factor=1 "
            "VoltageChangeTolerance=0.01 "
            "VarChangeTolerance=0.01 "
            "EventLog=Yes"
        )

    with open(
        arquivo_dss,
        "w",
        encoding="utf-8"
    ) as f:
        f.write("\n".join(linhas))

    if not volt_var:
        resumo.to_excel(
            cfg.COM_PV /
            f"geradoresPV_{int(100 * penetracaoPV)}.xlsx",
            index=False
        )

    print(
        f"\nGerado {arquivo_dss.name}."
    )


def gera_master_pv(
        nivelPV,
        volt_var=False
        ):

    sufixo = "_VV" if volt_var else ""

    arquivo = (
        cfg.COM_PV /
        f"PV_Master{int(100 * nivelPV)}{sufixo}.dss"
    )

    arquivo_pv = (
        cfg.COM_PV /
        f"geradoresPV_{int(100 * nivelPV)}{sufixo}.dss"
    )

    with open(
            arquivo,
            "w"
            ) as f:

        f.write(
            f"Redirect {arquivo_pv}\n"
        )

    print(
        f"\nGerado {arquivo.name}."
    )


def plota_distribuicao(resumo, penetracao):
    
    resumo = resumo.sort_values("Carga_kW")
    
    x = np.arange(len(resumo))
    
    # Plot 1 - Load and PV by bus
    plt.figure(figsize=(12, 6))

    plt.bar(
        x,
        resumo["Carga_kW"],
        label="Load"
    )
    
    plt.bar(
        x,
        resumo["PV_kW"],
        label="PV"
    )
    
    plt.grid()
    plt.legend()
    plt.xlabel("Buses (sorted by load)")
    plt.ylabel("Power (kW)")
    plt.title(
        f"Load and PV distribution 60% penetration" #" ({100*penetracao:.0f}% penetration)"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()
    
    # Plot 2 - Load vs. PV scatter plot
    plt.figure(figsize=(8, 6))
    
    plt.scatter(
        resumo["Carga_kW"],
        resumo["PV_kW"],
        s=15
    )
    
    plt.grid()
    plt.xlabel("Load (kW)")
    plt.ylabel("Installed PV (kW)")
    plt.title(
        f"Installed PV power versus load 60% penetration" #" ({100*penetracao:.0f}% penetration)"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()


def plota_sistemas_pv(distribuicao, penetracao):

    potencias = [
        pv["potencia"]
        for pv in distribuicao
        ]
    
    plt.figure(figsize=(10,5))
    
    plt.hist(
        potencias,
        bins=np.arange(0, 21.5, 0.5),
        edgecolor="black"
        )
    
    plt.grid()
    plt.xlabel("Potência dos PVs (kW)")
    plt.ylabel("Quantidade de sistemas")
    plt.title(
        f"Distribuição das potências dos sistemas PV\n"
        f"Cenário com {penetracao:.2f} kW de FV"
    )
    
    plt.tight_layout()
    plt.show()
    plt.close()
     
# Função principal da Etapa 5
def gerar_dss(
        cenarios,
        nivelPV
        ):

    resumo_final = []

    for (
            penetracao,
            dados
            ), nivel in zip(
                cenarios.items(),
                nivelPV
            ):

        # ======================================================
        # CENÁRIO ORIGINAL - FP = 1
        # ======================================================

        geradoresPVs_dss(
            dados["distribuicao"],
            dados["resumo"],
            nivel,
            volt_var=False
        )

        gera_master_pv(
            nivel,
            volt_var=False
        )

        # ======================================================
        # CENÁRIO VOLT-VAR
        # ======================================================
        # Mesma distribuição de PVs; apenas acrescenta InvControl.
        # ======================================================

        geradoresPVs_dss(
            dados["distribuicao"],
            dados["resumo"],
            nivel,
            volt_var=True
        )

        gera_master_pv(
            nivel,
            volt_var=True
        )

        plota_distribuicao(
            dados["resumo"],
            nivel
        )

        resumo_final.append({

            "Penetracao":
                100 * nivel,

            "Potencia":
                dados["resumo"]["PV_kW"].sum(),

            "Numero_PVs":
                len(
                    dados["distribuicao"]
                )
        })

    resumo_final = pd.DataFrame(
        resumo_final
    )

    resumo_final.to_excel(
        cfg.LOG_CENARIOS,
        index=False
    )

    print("\n")
    print(
        resumo_final
    )

    plota_distribuicao(
        dados["resumo"],
        penetracao
    )

    plota_sistemas_pv(
        dados["distribuicao"],
        penetracao
    )


# Step 6 - Additional plots
# Plot baseline load (average daytime load) and PV penetration levels
def plota_baseload_nivelPV(curva, carga_media, potenciasPV, niveisPV):
    
    plt.figure(figsize=(10, 6))
    
    plt.plot(
        curva.index,
        curva.values,
        linewidth=3,
        color="black",
        label="Average load"
    )
    
    plt.axhline(
        carga_media,
        color="red",
        linestyle="--",
        label="Average daytime load without PV"
    )
    
    cores = [
        "green",
        "blue",
        "orange",
        "purple"
    ]
    
    for i, (potencia, nivel) in enumerate(zip(potenciasPV, niveisPV)):

        plt.axhline(
            potencia,
            color=cores[i],
            linestyle=":",
            linewidth=2,
            label=f"{100*nivel:.0f}% ({potencia:.0f} kW)"
        )
    
    plt.grid()
    plt.xlabel("Hour")
    plt.ylabel("Power (kW)")
    plt.title("Average Daytime Load and PV Penetration Levels")
    plt.legend()
    plt.tight_layout()
    plt.show()
#####################################################################
# PRINCIPAL
#####################################################################
def main():

    # Percentuais de penetração PV desejados
    percentual_de_PVs = [
        0.20,
        0.40,
        0.60
    ]

    # Etapa 1 - Leitura do baseload e calculo da carga média diurna no barramento da
    # subestação.Leitura da curva de potência ativa do barramento da subestação, sem PV.
    carga_media, curva = calcula_media_diurna(
        cfg.RESULTADOS_BASE
    )
    
    # Etapa 2 - Determina a potência PV total (Potência alvo) a ser inserida;
    total_PV = calcula_potencia_PV_alvo(
        carga_media,
        percentual_de_PVs
    )
    
    salvar_potencias_cenarios(
        percentual_de_PVs,
        total_PV
    )

    # Etapa 3 - Leitura dos arquivos Loadshapes.dss para coletar dados dos
    # bus (identificador e carga)
    dados_cargas = buscar_dados_buses(
        [
            cfg.L_FEEDERA,
            cfg.L_FEEDERB,
            cfg.L_FEEDERC
        ],
        [
            getattr(cfg, 'LOADS_FEEDERA', cfg.L_FEEDERA),
            getattr(cfg, 'LOADS_FEEDERB', cfg.L_FEEDERB),
            getattr(cfg, 'LOADS_FEEDERC', cfg.L_FEEDERC)
        ]
    )

    # Etapa 4 - Realiza a inserção dos PVs
    cenarios = GERA_POPULACAO_PVs(
        dados_cargas,
        percentual_de_PVs,
        total_PV
    )

    # Etapa 5 - Construção dos arquivos .dss
    gerar_dss(cenarios, percentual_de_PVs)

    # Etapa 6 - Plota curvas baseload (carga média diurna) e níveis PV 
    plota_baseload_nivelPV(
        curva,
        carga_media,
        total_PV,
        percentual_de_PVs
    )
    
    print("\nPROCESSAMENTO CONCLUÍDO")

main()