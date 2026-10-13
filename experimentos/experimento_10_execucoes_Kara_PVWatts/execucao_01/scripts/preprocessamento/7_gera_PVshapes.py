#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera os arquivos de LoadShape e TShape utilizados pelo OpenDSS para simular
a geração fotovoltaica.

O script realiza:
    + Leitura do arquivo com dados climáticos processados;
    + Cria o arquivo "PVShape.txt" contendo os multiplicadores
    normalizados de irradiância.
    + Cria o arquivo "TempShape.txt" contendo série horária
    de temperatura ambiente.
    + Cria o arquivo "PV_Clima.dss"
    
ENTRADAS:
    CLIMA_PROCESSADOS
    
SAÍDAS:
    PVShape.txt
    TempShape.txt
    PV_Clima.dss

"""


import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg


############################################################
# FUNÇÃO SALVA ARQUIVO
def salva_txt(vetor, arquivo):

    with open(arquivo, "w") as f:

        for valor in vetor:

            f.write(f"{valor:.6f}\n")


############################################################
# PRINCIPAL


# Carrega arquivo
df = pd.read_excel(cfg.CLIMA_PROCESSADOS)

# Normaliza irradiância considerando valor base = 1000W/m²
if "irradiancia_W_m2" in df.columns:

    irradiancia = (df["irradiancia_W_m2"] / 1000).values

else:
    print("Coluna irradiancia_W_m2 não encontrada.")

# Le Temperatura
if "temperatura" in df.columns:
    
    temperatura = df["temperatura"].values

else:
    print("Coluna temperatura não encontrada.")

# Definição dos arquivos .txt
arquivo_pv = (cfg.INPUTS_DIR / "PV_shapes" / "PVShape.txt")

arquivo_temp = (cfg.INPUTS_DIR / "PV_shapes" / "TempShape.txt")

salva_txt(irradiancia, arquivo_pv)

salva_txt(temperatura, arquivo_temp)

# Cria arquivo DSS
arquivo_dss = (cfg.INPUTS_DIR / "PV_shapes" / "PV_Clima.dss")

with open(arquivo_dss, "w") as f:

    f.write(
        f"New LoadShape.PVShape "
        f"npts={len(irradiancia)} "
        f"interval=1 "
        f"mult=(file={arquivo_pv})\n"
    )

    f.write(
        f"New TShape.TempShape "
        f"npts={len(temperatura)} "
        f"interval=1 "
        f"temp=(file={arquivo_temp})\n"
    )



print(f"\nIrradiância: {len(irradiancia)} pontos")

print(f"Temperatura: {len(temperatura)} pontos")

print(f"\nArquivo .dss salvo em: \n{arquivo_dss}")

print("\nProcessamento concluído")

