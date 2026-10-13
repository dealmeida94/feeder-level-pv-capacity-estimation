"""
Gera um arquivo Load.dss para cada Feeder a partir das configurações de cada
load, dos loadshapes e dos valores de base utilizados para normalização das series
de dados presentes nos loadshapes.

INPUTS:
    - Arquivo .xlsx com as configurações dos loads;
    - Arquivos .csv com os valores de base;
    - Arquivos loadshapes.dss.

OUTPUTS:
    - Arquivos Load.dss por feeder;
    - Log em .xlsx.
    

@author: matheus

"""

import pandas as pd
import re
import time
import sys
from pathlib import Path
from auxiliares import calc_tempo 

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg

# Inicializa contador de tempo
begin_timer = time.perf_counter()

# Função para extrair informações dos arquivos loadshapes
def get_inf_ls(loadshape_dss):
    # Inicializa um dicionário
    loadshapes = {}

    # Abre o arquivo
    with open(loadshape_dss, "r") as f:
        for linha in f:
            # Retira espaços em branco antes e após as strings
            linha = linha.strip()

            # Converte todos os caracteres para minusculo e 
            # verifica se a string inicia com o padrão 'new loadshape'
            # Se a linha não inicia com 'new loadshape' pode ser ignorada
            if not linha.lower().startswith("new loadshape"):
                continue

            # O declaração de cargas no arquivo Load.dss possui a seguinte estrutura: 
            #   New  Load.Load_1003  phases=3  conn=wye  bus1=T_bus1003_L.1.2.3.0  kV=0.208  kW=15.290000000000001    Kvar=3.832035216364534 
            #   -> Load name, number of phses, connection, bus, kV rating, active power, reactive power
            
            # Extrai nome do loadshape
            palavras = linha.split()
            nome_ls = None
            for palavra in palavras:
                if "loadshape." in palavra.lower():
                    # Atribui a variavel 'nome_ls' o nome do Load 
                    nome_ls = palavra.split(".")[1]
                    break
            
            if not nome_ls:
                print(f"Não foi possível identificar o nome do load na linha:\n{linha}")
                continue

            # Extrai número do bus
            padrao_bus = re.search(r"(\d+)", nome_ls)
            if not padrao_bus:
                print(f"Não encontrou número no nome:\n{nome_ls}")
                continue
            numero_bus = str(int(padrao_bus.group(1)))
            chave_bus = f"Bus {numero_bus}"

            loadshapes[chave_bus] = nome_ls

    return loadshapes


#########################################################
################# FUNÇÃO processa_dados #################

def processa_dados(feeder):
    df_configs = pd.read_excel(cfg.CFG_LOAD, sheet_name=f"Feeder_{feeder}")
    df_bases = pd.read_csv(cfg.BASE_LOAD / f"Valores_de_Base_Feeder{feeder}.csv")
    loadshapes_dss = cfg.BASE_LOAD / f"Loadshapes_Feeder{feeder}.dss"

    # Padroniza colunas
    df_configs.columns = [c.lower() for c in df_configs.columns]
    df_bases.columns = [c.lower() for c in df_bases.columns]

    # Padroniza BUS (remove zeros à esquerda)
    df_bases["bus"] = (
        df_bases["bus"]
        .astype(str)
        .str.extract(r"(\d+)")[0]
        .astype(int)
        .astype(str)
    )

    loadshapes = get_inf_ls(loadshapes_dss)

    if not loadshapes:
        print(f"Erro!!! Nenhum loadshape encontrado para o feeder {feeder}")

    return df_bases, df_configs, loadshapes


#########################################################
################# FUNÇÃO gera_loads #####################

def gera_loads(valores_bases, configuracoes, loadshapes, feeder):
    linhas_saida = {feeder: []}
    faltantes_ls = []
    faltantes_base = []

    for _, row in configuracoes.iterrows():

        load = str(row["load"])
        bus = str(row["bus1"])
        phases = int(row.get("phases", 3))
        conn = row.get("conn", "wye")

        # Extrai ID numérico do load
        padrao = re.search(r"(\d+)", load)
        if not padrao:
            continue

        load_id = str(int(padrao.group(1)))  # padroniza
        chave_bus = f"Bus {load_id}"

        # Verifica loadshape
        nome_ls = loadshapes.get(chave_bus)
        if nome_ls is None:
            faltantes_ls.append(load)
            continue

        # Verifica base
        base_row = valores_bases[valores_bases["bus"] == load_id]
        if base_row.empty:
            faltantes_base.append(load)
            continue

        kw = float(base_row["p_base"].values[0])

        linha = (
            f"New Load.{load} "
            f"phases={phases} conn={conn} "
            f"bus1={bus} "
            f"kV=0.208 "
            f"kW={kw:.3f} "
            f"yearly={nome_ls} model=1"
        )

        linhas_saida[feeder].append(linha)

    print(f"\nFeeder {feeder}: {len(linhas_saida[feeder])} loads gerados")
    print(f"Sem loadshape: {len(faltantes_ls)}")
    print(f"Sem base: {len(faltantes_base)}")

    return linhas_saida, faltantes_ls, faltantes_base


#########################################################
################# FUNÇÃO salva_relatorio ################

def salva_relatorio(faltantes_ls, faltantes_base, caminho_arquivo):

    df_ls = pd.DataFrame({"load_sem_loadshape": faltantes_ls})
    df_base = pd.DataFrame({"load_sem_base": faltantes_base})

    with pd.ExcelWriter(caminho_arquivo, engine="openpyxl") as writer:
        df_ls.to_excel(writer, sheet_name="Sem_Loadshape", index=False)
        df_base.to_excel(writer, sheet_name="Sem_Base", index=False)

    print(f"Relatório salvo em: {caminho_arquivo}")


#########################################################
######################## MAIN ###########################


feeders = ["A", "B", "C"]

for feeder in feeders:

    bases, configs, ls = processa_dados(feeder)

    linhas_por_feeder, faltantes_ls, faltantes_base = gera_loads(
        bases, configs, ls, feeder
    )

    for fdr, linhas in linhas_por_feeder.items():

        arquivo_saida = cfg.BASE_LOAD / f"Loads_Feeder{fdr}.dss"

        with open(arquivo_saida, "w") as f:
            f.write(f"! Arquivo Load - Feeder {fdr}\n")

            for linha in linhas:
                f.write(linha + "\n")

    print(f"Arquivo Load.dss salvo em: {arquivo_saida}")

    salva_relatorio(
        faltantes_ls,
        faltantes_base,
        cfg.LOG_GERA_LOAD,
    )
    
end_timer = time.perf_counter()
tempo = calc_tempo(begin_timer,end_timer)
print(f"\n\nTempo de execução: {tempo}")