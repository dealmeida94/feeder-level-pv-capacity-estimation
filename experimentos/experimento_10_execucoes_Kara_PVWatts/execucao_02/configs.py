"""
Arquivo que define os caminhos e nomes dos arquivos de entrada e saída.

Seu objetivo é centralizar essas configurações, tornando muito mais fácil
alterar essas informações posteriormente.

@author: matheus
"""

from pathlib import Path

# Verifica a pasta raiz do projeto
RAIZ_DIR = Path(__file__).resolve().parent

# DADOS EXTERNOS
EXT_DIR = RAIZ_DIR / "dados" / "externos"
NODAL_PQ = EXT_DIR / "Calculated Nodal P&Q.xlsx"
DADOS_CLIMA = EXT_DIR / "estacao_INMET_A853_cruz_alta.csv"
LOAD_DSS_ORIGINAL = EXT_DIR / "Load_Original.dss"
MASTER_DSS_ORGINAL = EXT_DIR / "Master_Original.dss"

# RELATÓRIOS
LOGS_DIR = RAIZ_DIR / "logs"
LOG_NODAL_PQ_txt = LOGS_DIR / "log_processamento_Nodal_PQ.txt"
LOG_GERA_LS = LOGS_DIR / "log_gera_loadshapes.txt"
LOG_GERA_LOAD = LOGS_DIR / "log_gera_load_dss.xlsx"
LOG_MASTER = LOGS_DIR / "logs_gera_Masterdss.txt"
LOG_CLIMA = LOGS_DIR / "logs_processamento-dados-climaticos.txt"
LOG_CENARIOS = LOGS_DIR / "logs_geracao_cenarios.txt"
LOG_SIMU_PV = LOGS_DIR / "log_simulacao_com_PV.xlsx"

# INPUTS
INPUTS_DIR = RAIZ_DIR / "dados" / "inputs"

BASE_LOAD = INPUTS_DIR / "carga_base"
L_FEEDERA = BASE_LOAD / "Loads_FeederA.dss"
L_FEEDERB = BASE_LOAD / "Loads_FeederB.dss"
L_FEEDERC = BASE_LOAD / "Loads_FeederC.dss"
LS_FEEDERA = BASE_LOAD / "Loadshapes_FeederA.dss"
LS_FEEDERB = BASE_LOAD / "Loadshapes_FeederB.dss"
LS_FEEDERC = BASE_LOAD / "Loadshapes_FeederC.dss"
MASTER_BL = BASE_LOAD / "Master_sem_PV.dss"

COM_PV = INPUTS_DIR / "cenario_com_PV"

# PVShape oficial da arquitetura atual (PVWatts).
PVSHAPE = COM_PV / "PVShape.dss"
 

# OUTPUTS
OUTPUTS_DIR = RAIZ_DIR / "dados" / "outputs"
OUT_BASE = OUTPUTS_DIR / "carga_base"
OUT_PV = OUTPUTS_DIR / "cenarios_PV"
RESULTADOS_BASE = OUT_BASE / "resultados_sem_PV.parquet"


# INTERMEDIARIOS
INTER_DIR = RAIZ_DIR / "dados" / "intermediarios"
PQ_SISTEMA = INTER_DIR / "Nodal_PQ_processado.xlsx"
CFG_LOAD = INTER_DIR / "configs_do_load.xlsx"
CLIMA_PROCESSADOS = INTER_DIR / "Dados_climaticos_processados.xlsx"

# ELEMENTOS
ELEM_DIR = RAIZ_DIR / "elementos_dss"

# FIGURAS
FIGS_DIR = RAIZ_DIR / "figuras"
# Etapa de preprocessamento
FIGS_PREPROC_DIR = FIGS_DIR / "pre-processamento"

FIGS_PV = FIGS_DIR / "cenarios_com_PV"

SUB_PQ_TOTAL = FIGS_PREPROC_DIR / "potencia_total_subestacao.png"
SUB_FP_TOTAL = FIGS_PREPROC_DIR / "FP_total_subestacao.png"

FEEDER_A_PQ_TOTAL = FIGS_PREPROC_DIR / "potencia_total_FeederA.png"
FEEDER_B_PQ_TOTAL = FIGS_PREPROC_DIR / "potencia_total_FeederB.png"
FEEDER_C_PQ_TOTAL = FIGS_PREPROC_DIR / "potencia_total_FeederC.png"
FEEDER_A_FP_TOTAL = FIGS_PREPROC_DIR / "FP_total_FeederA.png"
FEEDER_B_FP_TOTAL = FIGS_PREPROC_DIR / "FP_total_FeederB.png"
FEEDER_C_FP_TOTAL = FIGS_PREPROC_DIR / "FP_total_FeederC.png"

SUB_PQ_1DIA = FIGS_PREPROC_DIR / "potencia_1DIA_subestacao.png"
SUB_FP_1DIA = FIGS_PREPROC_DIR / "FP_1DIA_subestacao.png"

FEEDER_A_PQ_1DIA = FIGS_PREPROC_DIR / "potencia_1DIA_FeederA.png"
FEEDER_B_PQ_1DIA = FIGS_PREPROC_DIR / "potencia_1DIA_FeederB.png"
FEEDER_C_PQ_1DIA = FIGS_PREPROC_DIR / "potencia_1DIA_FeederC.png"
FEEDER_A_FP_1DIA = FIGS_PREPROC_DIR / "FP_1DIA_FeederA.png"
FEEDER_B_FP_1DIA = FIGS_PREPROC_DIR / "FP_1DIA_FeederB.png"
FEEDER_C_FP_1DIA = FIGS_PREPROC_DIR / "FP_1DIA_FeederC.png"

FEEDERS_PQ_PATH = {
    "FeederA" : FEEDER_A_PQ_TOTAL,
    "FeederB" : FEEDER_B_PQ_TOTAL,
    "FeederC" : FEEDER_C_PQ_TOTAL
}

FEEDERS_FP_PATH = {
    "FeederA" : FEEDER_A_FP_TOTAL,
    "FeederB" : FEEDER_B_FP_TOTAL,
    "FeederC" : FEEDER_C_FP_TOTAL
}

FEEDERS_PQ1D_PATH = {
    "FeederA" : FEEDER_A_PQ_1DIA,
    "FeederB" : FEEDER_B_PQ_1DIA,
    "FeederC" : FEEDER_C_PQ_1DIA
}

FEEDERS_FP1D_PATH = {
    "FeederA" : FEEDER_A_FP_1DIA,
    "FeederB" : FEEDER_B_FP_1DIA,
    "FeederC" : FEEDER_C_FP_1DIA
}

DIARIAS_IRRAD = FIGS_PREPROC_DIR / "Curvas_diarias_de_irradiancia.png"
NASCER_POR_SOL = FIGS_PREPROC_DIR / "Nascer_e_por_do_sol_ao_longo_do_ano.png"
DURACAO_DIA = FIGS_PREPROC_DIR / "Duracao_do_dia_ao_longo_do_ano.png"
CLUSTERS = FIGS_PREPROC_DIR / "Clusters_de_irradiancia.png"
CENTROIDES = FIGS_PREPROC_DIR / "Centroides_de_irradiancia.png"



#Execução
# Baseload
FIGS_BS_DIR = FIGS_DIR / "base-load"
BS_PQ_SUBESTACAO = FIGS_BS_DIR / "PeQ_subestacao_baseload.png" 
BS_FP_SUBESTACAO = FIGS_BS_DIR / "FP_subestacao_baseload.png"
BS_V_SUBESTACAO = FIGS_BS_DIR / "V_subestacao_baseload.png"




# ============================================================================
# ESTIMAÇÃO DE POTÊNCIA PV
#
# Resultados intermediários da simulação utilizados pelo estimador.
# Os diretórios podem ser alterados aqui sem modificar os scripts.
#
# Por padrão, FP=1 utiliza a pasta atual de clusters. Para Volt-VAr, o
# diretório é separado para que os dois experimentos nunca sejam misturados.

CLUSTERS_DIR = OUTPUTS_DIR / "clusters"
CLUSTERS_FP1 = CLUSTERS_DIR / "FP1"
CLUSTERS_VV = CLUSTERS_DIR / "VoltVar"

# Arquivo com a potência PV realmente instalada em cada cenário.
POTENCIAS_CENARIOS = LOGS_DIR / "Potencias_Cenarios.xlsx"

# Resultados produzidos pelo estimador.
OUT_ESTIMACAO = OUTPUTS_DIR / "estimacao_PV"
