'''
Realiza uma leitura da planilha "Nodal_PQ_processados.xlsx", e gera
arquivos loadshapes de potência ativa (P com valores em p.u (normalizado por unidade).

Etapas do processo:
    1. Leitura dos dados
    2. Eliminação de cargas nulas
    3. Para cada bus, adota o valor máximo de potência como valor de base
    4. Realiza a normalização dos valores em cada bus
    5. Salva loadshapes em arquivos .txt
    6. Gera arquivos loadshapes.dss
    7. Salva os valores bases em uma planilha .csv
    
@author: matheus
    
'''

import pandas as pd
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg

# Função que realiza cada etapa do processamento
# por Feeder
def processar_feeder(feeder):

    # 1. Leitura dos dados
    df = pd.read_excel(cfg.PQ_SISTEMA, sheet_name=f"{feeder}_P")

    # Remove coluna "Time"
    for col in df.columns:
        if str(col) == "Time":
            df = df.drop(columns=[col])

    # Todos os dados convertidos para tipo numérico
    df = df.apply(pd.to_numeric, errors="coerce")
    
    # 2. Elimina cargas nulas
    df = df.loc[:, (df != 0).any(axis=0)]
    
    # Cria um novo dataframe para salvar valores de base
    df_base = pd.DataFrame(columns=["Bus", "P_base"])

    # Inicializa uma lista para armazenar as linhas que vão compor o
    # arquivo loadshape.dss
    linhas_dss = []

    # Para cada bus
    for bus in df.columns:

        # Copia as medições de potência do bus para a variável serie
        serie = df[bus]
        
        # 3. Determina o valor máximo da serie como valor de base
        P_base = serie.max()
        
        # 4. Converte valores da serie para p.u
        pu = serie / P_base

        # 5. Salva os loadshapes em arquivos .txt
        bus = bus.replace(" ", "_")
        caminho = cfg.BASE_LOAD / f"{feeder}" / f"{feeder}_{bus}.txt"
        pu.to_csv(caminho, index=False, header=False)

        # 6. Gera arquivo Load.dss
        # nome do load
        nome = f"Load_{bus}"
        
        # nº de pontos 8760 (1 ano), intervalo = 1 hora
        # file = caminho p/ .txt com loadshape
        linha = (
            f"New Loadshape.{nome} "
            f"npts=8760 interval=1 "
            f"mult=(file={caminho})"
        )
        
        linhas_dss.append(linha)
        df_base.loc[len(df_base)] = [bus, P_base]
    
        
    # Salva arquivo       
    loadshape_dss = cfg.BASE_LOAD / f"Loadshapes_{feeder}.dss"
    with open(loadshape_dss, "w") as f:
        f.write(f"// Loadshapes do {feeder}\n")
        f.write("// Dados normalizados em PU\n")
        f.write("// Valores de base salvos em: \n")
        f.write(f"// {cfg.BASE_LOAD} / {feeder}_bases.csv \n\n")

        for linha in linhas_dss:
            f.write(linha + "\n")

    # 7. Salva valores de base
    caminho_Vbase = cfg.BASE_LOAD / f"Valores_de_Base_{feeder}.csv"
    df_base.to_csv(caminho_Vbase, index=False)

    # FIM DA FUNÇÃO
    
###################################################################################    

# EXECUTA O PROCESSAMENTO

# Inicia contador de tempo
begin_timer = time.perf_counter()

print ('Processamento iniciado')

feeders = ["FeederA", "FeederB", "FeederC"]
    
for feeder in feeders:
    processar_feeder(feeder)


# Finaliza contador de tempo
end_timer = time.perf_counter()    
# Calcula tempo transcorrido
tempo = end_timer - begin_timer
minutos = int(tempo // 60)
segundos = int(tempo % 60)

print("\nProcesso finalizado!")
print(f"Tempo de processamento: {minutos:02d}m:{segundos:02d}s")

# Salva relatório
with open(cfg.LOG_GERA_LS, "w") as f:
    f.write(f"Tempo de processamento: {minutos:02d}m:{segundos:02d}s")
    f.write("\n\nLoadshapes por Bus (.txt) salvos em:")
    f.write(f"\n\t{cfg.BASE_LOAD}/FeederA")
    f.write(f"\n\t{cfg.BASE_LOAD}/FeederB")
    f.write(f"\n\t{cfg.BASE_LOAD}/FeederC")
    f.write("\n\nArquivos Loadshapes.dss salvos em:")
    f.write(f"\n\t{cfg.BASE_LOAD}")