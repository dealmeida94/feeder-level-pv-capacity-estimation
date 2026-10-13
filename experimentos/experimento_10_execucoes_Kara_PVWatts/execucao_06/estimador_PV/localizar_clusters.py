
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Localiza os clusters gerados na pasta indicada.

A pasta é selecionada de acordo com a condição experimental:
    - FP1   -> clusters FP=1
    - VV    -> clusters Volt-VAr

Retorna uma lista de dicionarios contendo o caminho para os clusters,
nome e cenário.
"""

from pathlib import Path
from collections import defaultdict

import sys

# ==========================================================
# RAIZ DO PROJETO
# ==========================================================

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import configs as cfg


# ==========================================================
# LOCALIZAÇÃO DOS CLUSTERS
# ==========================================================

def localizar_clusters(tipo="FP1"):

    # ------------------------------------------------------
    # Seleciona a pasta conforme a condição experimental
    # ------------------------------------------------------

    if tipo == "FP1":
        pasta = Path(cfg.CLUSTERS_FP1)

    elif tipo == "VV":
        pasta = Path(cfg.CLUSTERS_VV)

    else:
        raise ValueError(
            "Tipo de cluster inválido. Use 'FP1' ou 'VV'."
        )

    lista_clusters = []

    # ------------------------------------------------------
    # Localiza os arquivos
    # ------------------------------------------------------

    arquivos = sorted(
        pasta.glob("Cluster_*.parquet")
    )

    if len(arquivos) == 0:
        print(
            f"Nenhum cluster encontrado em: {pasta}"
        )
        return lista_clusters

    # ------------------------------------------------------
    # Processa cada arquivo
    # ------------------------------------------------------

    for arquivo in arquivos:

        nome = arquivo.stem

        partes = nome.split("_")

        # ==================================================
        # FP1
        #
        # Exemplo:
        # Cluster_1_20.parquet
        #
        # partes = ["Cluster", "1", "20"]
        # ==================================================

        if tipo == "FP1":

            if len(partes) != 3:

                print(
                    f"Ignorando arquivo com nome inválido: "
                    f"{arquivo.name}"
                )

                continue

            _, cluster, cenario = partes

        # ==================================================
        # VOLT-VAR
        #
        # Exemplo:
        # Cluster_1_20_VV.parquet
        #
        # partes = ["Cluster", "1", "20", "VV"]
        # ==================================================

        elif tipo == "VV":

            if len(partes) != 4 or partes[3] != "VV":

                print(
                    f"Ignorando arquivo com nome inválido: "
                    f"{arquivo.name}"
                )

                continue

            _, cluster, cenario, _ = partes

        # --------------------------------------------------
        # Converte cluster e cenário para inteiro
        # --------------------------------------------------

        try:

            cluster = int(cluster)
            cenario = int(cenario)

        except ValueError:

            print(
                f"Ignorando arquivo com nome inválido: "
                f"{arquivo.name}"
            )

            continue

        # --------------------------------------------------
        # Ignora o cenário base (0% PV)
        # --------------------------------------------------

        if cenario == 0:
            continue

        # --------------------------------------------------
        # Aceita somente os cenários utilizados na estimação
        # --------------------------------------------------

        if cenario not in (20, 40, 60):
            print(
                f"Ignorando cenário não utilizado: "
                f"{arquivo.name}"
            )
            continue

        # --------------------------------------------------
        # Armazena o cluster
        # --------------------------------------------------

        lista_clusters.append({
            "cluster": cluster,
            "cenario": cenario,
            "arquivo": arquivo
        })

    # ======================================================
    # ORGANIZAÇÃO PARA EXIBIÇÃO
    # ======================================================

    cenarios = defaultdict(list)

    for item in lista_clusters:

        cenarios[item["cenario"]].append(
            item["cluster"]
        )

    # ======================================================
    # MENSAGEM
    # ======================================================

    nome_tipo = (
        "FP = 1"
        if tipo == "FP1"
        else "Volt-VAr"
    )

    print(
        f"\nForam localizados "
        f"{len(lista_clusters)} clusters "
        f"para {nome_tipo} em:"
        f"\n{pasta}\n"
    )

    for cenario in sorted(cenarios):

        print(f"Cenário {cenario}%")

        for cluster in sorted(cenarios[cenario]):

            print(f"   Cluster {cluster}")

        print()

    return lista_clusters

