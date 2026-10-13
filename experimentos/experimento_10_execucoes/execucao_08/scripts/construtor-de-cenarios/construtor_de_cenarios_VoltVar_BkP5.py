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
    """
    dados = []
    for percentual, potencia in zip(percentuais, potencias):
        dados.append({
            "Penetracao": 100.0 * percentual,
            "Potencia_PV_alvo_kW": round(float(potencia), 3)
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

    print(f"\nLoads elegíveis encontrados: {len(dados_buses)}")

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


def _quotas_fases_feeder(estado_buses, feeder, n_pvs, populacao_feeder):
    """Calcula quotas de PVs mono/bi/tri dentro de um feeder.

    A base é a composição real dos loads. PVs de 10/15/20 kW são reservados
    obrigatoriamente para cargas trifásicas. Se a quantidade desses PVs for
    maior que a quota trifásica natural, a quota tri é ampliada e as demais
    quotas são reduzidas proporcionalmente.
    """
    fases = (1, 2, 3)
    subset = [x for x in estado_buses if x["feeder"] == feeder]
    contagem = {f: sum(x["phases"] == f for x in subset) for f in fases}

    quotas = _maior_resto_alocacao(contagem, n_pvs)

    n_tri_obrigatorios = sum(
        pv["potencia"] in POTENCIAS_PV_TRIFASICAS
        for pv in populacao_feeder
    )

    if n_tri_obrigatorios > quotas[3]:
        deficit = n_tri_obrigatorios - quotas[3]
        quotas[3] = n_tri_obrigatorios

        # Retira primeiro de classes não-trifásicas com maior quota.
        for fase in sorted((1, 2), key=lambda fase: quotas[fase], reverse=True):
            retirada = min(deficit, quotas[fase])
            quotas[fase] -= retirada
            deficit -= retirada
            if deficit == 0:
                break

        if deficit > 0:
            # Isto só pode ocorrer se o feeder tiver poucos/nenhum loads
            # não-trifásicos. Mantemos a soma correta sem criar fase inválida.
            quotas[3] = max(n_tri_obrigatorios, n_pvs - quotas[1] - quotas[2])

    print(
        f"    Feeder {feeder} - quota de fases: "
        f"mono={quotas[1]} | bi={quotas[2]} | tri={quotas[3]} "
        f"(loads: mono={contagem[1]} | bi={contagem[2]} | tri={contagem[3]})"
    )

    return quotas


def _escolher_bus_ponderado(candidatos, potencia):
    """Escolhe aleatoriamente um bus, favorecendo menor penetração acumulada."""
    pesos = []
    for bus in candidatos:
        limite = 0.40 * bus["kw"]
        capacidade_restante = max(0.0, limite - bus["pv_instalado"])
        penetracao = bus["pv_instalado"] / bus["kw"] if bus["kw"] > 0 else 1.0
        peso = max(0.05, 1.0 - penetracao) * max(0.05, capacidade_restante)
        pesos.append(peso)

    return random.choices(candidatos, weights=pesos, k=1)[0]


def distribuir_PVs(
        dados_bus,
        populacao_PV,
        max_pot_PV=0.40
        ):
    """Distribui PVs por quotas de feeder e de fase.

    Metodologia:
      1. calcula a quota de PVs de cada feeder combinando 50% da proporção
         de loads e 50% da proporção de potência dos loads;
      2. dentro de cada feeder, calcula quotas mono/bi/tri pela composição
         real das cargas;
      3. garante que 10/15/20 kW sejam sempre trifásicos;
      4. mantém aleatoriedade somente na escolha dos buses dentro de cada
         grupo feeder+fase, preservando a variabilidade espacial entre
         experimentos;
      5. respeita o limite de 40% da carga por bus.
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

    # O tamanho da população continua aleatório; a alocação dos PVs aos
    # feeders é controlada por quota. Embaralhamos para não associar
    # sistematicamente os maiores PVs a um feeder específico.
    populacao_embaralhada = populacao_PV.copy()
    random.shuffle(populacao_embaralhada)

    por_feeder = {f: [] for f in ("A", "B", "C")}
    indice = 0
    for feeder in ("A", "B", "C"):
        quantidade = quotas_feeders[feeder]
        por_feeder[feeder] = populacao_embaralhada[indice:indice + quantidade]
        indice += quantidade

    # Cada PV recebe primeiro uma fase-alvo. Para 10/15/20 kW a fase 3 é
    # obrigatória; os demais seguem as quotas baseadas nos loads.
    for feeder in ("A", "B", "C"):
        pvs_feeder = por_feeder[feeder]
        if not pvs_feeder:
            continue

        quotas_fases = _quotas_fases_feeder(
            estado_buses,
            feeder,
            len(pvs_feeder),
            pvs_feeder
        )

        # Cria uma lista de fases com a quota exata. Os PVs trifásicos são
        # colocados primeiro para garantir sua restrição.
        fases_alocadas = []
        for fase in (1, 2, 3):
            fases_alocadas.extend([fase] * quotas_fases[fase])

        random.shuffle(fases_alocadas)

        # Se algum PV grande cair numa fase 1/2, troca com uma posição tri.
        for i, pv in enumerate(pvs_feeder):
            if pv["potencia"] in POTENCIAS_PV_TRIFASICAS and fases_alocadas[i] != 3:
                j = next(
                    (j for j in range(i + 1, len(fases_alocadas))
                     if fases_alocadas[j] == 3),
                    None
                )
                if j is not None:
                    fases_alocadas[i], fases_alocadas[j] = 3, fases_alocadas[i]

        for pv, fase_alvo in zip(pvs_feeder, fases_alocadas):
            potencia = pv["potencia"]

            candidatos = [
                bus for bus in estado_buses
                if bus["feeder"] == feeder
                and bus["phases"] == fase_alvo
                and _fase_compativel(pv, bus)
                and bus["pv_instalado"] + potencia <= max_pot_PV * bus["kw"]
            ]

            # Se a quota de fase não puder ser atendida por capacidade de
            # bus, tenta outra fase fisicamente compatível, sem violar a
            # regra dos PVs obrigatoriamente trifásicos.
            if not candidatos:
                fases_alternativas = [3] if potencia in POTENCIAS_PV_TRIFASICAS else [1, 2, 3]
                candidatos = [
                    bus for bus in estado_buses
                    if bus["feeder"] == feeder
                    and bus["phases"] in fases_alternativas
                    and _fase_compativel(pv, bus)
                    and bus["pv_instalado"] + potencia <= max_pot_PV * bus["kw"]
                ]

                if candidatos:
                    print(
                        f"AVISO: quota de fase não pôde ser atendida para "
                        f"{pv['nome']} ({potencia:.1f} kW) no Feeder {feeder}. "
                        f"Usando fase alternativa compatível."
                    )

            if not candidatos:
                print(
                    f"AVISO: não foi possível alocar {pv['nome']} "
                    f"({potencia:.1f} kW) no Feeder {feeder}."
                )
                continue

            bus = _escolher_bus_ponderado(candidatos, potencia)
            bus["pv_instalado"] += potencia
            bus["numero_pvs"] += 1

            distribuicao.append({
                "nome": pv["nome"],
                "bus": bus["bus"],
                "phases": bus["phases"],
                "conn": bus["conn"],
                "feeder": bus["feeder"],
                "potencia": potencia
            })

    potencia_solicitada = sum(pv["potencia"] for pv in populacao_PV)
    potencia_distribuida = sum(pv["potencia"] for pv in distribuicao)

    if potencia_distribuida < potencia_solicitada:
        print("\nATENÇÃO: nem toda a potência da população PV foi alocada.")
        print(f"  Solicitada : {potencia_solicitada:.2f} kW")
        print(f"  Distribuída: {potencia_distribuida:.2f} kW")

    print("\nDISTRIBUIÇÃO FINAL POR FEEDER:")
    stats = _estatisticas_feeders(estado_buses)
    for feeder in ("A", "B", "C"):
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