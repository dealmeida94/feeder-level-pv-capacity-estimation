#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Realiza o processamento das medições de radiação solar e temperatura
fornecidas pelas estação do INMET A853 (Cruz Alta/RS).

O processamento é dividido nas seguintes etapas:
    - Leitura do dados;
    - Conversão de radiação para irradiância;
    - Inputação de dados faltantes;
    - Cálculo astronômico do nascer e pôr do sol;
    - Clusterização das curvas diárias;
    - Calculos estatísticos;
    - Plotagens de gráficos;
    - Salva relatório do processamento.
    
INPUTS:
    + Tabela fornecida pelo site do INMET
    
OUTPUTS:
    + Arquivo .xlsx contendo os dados processados
    + Figuras .png contendo os plots
    + Arquivo .txt com relatório do processamento

"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from astral import LocationInfo
from astral.sun import sun
from sklearn.cluster import KMeans
from datetime import timedelta
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg

############################################################
# CONFIGURAÇÕES
# Coordenadas da estação meteorológica
LATITUDE = -28.6
LONGITUDE = -53.6
# Fuso horário
TIMEZONE = "America/Sao_Paulo"
# Número de clusters
N_CLUSTERS = 3

############################################################
# FUNÇÕES DE RELATÓRIO

# Inicializa uma lista
relatorio = []

def mostrar_salvar(msg):
    print(msg)
    relatorio.append(str(msg))

def salvar_relatorio():
    with open(cfg.LOG_CLIMA,"w", encoding="utf-8") as file:
        file.write("\n".join(relatorio))

############################################################
# FUNÇÕES DE PROCESSAMENTO

def ajusta_hora(h):
    # Hora no arquivo do INMET no formato 0100, 0200, 0300
    # converte para o formato 01:00, 02:00, 03:00
    h = str(h).zfill(4)
    return f"{h[:2]}:{h[2:]}"

def decimal_para_hhmm(h):

    # Converte uma hora decimal para o formato HH:MM.
    horas = int(h)

    minutos = int(round((h - horas) * 60))

    # Evita que o minuto seja 60
    if minutos == 60:
        horas += 1
        minutos = 0

    return f"{horas:02d}:{minutos:02d}"

def carregar_dados():
    df = pd.read_csv(
        cfg.DADOS_CLIMA,
        sep=";",
        decimal=",",
        encoding="utf-8"
    )

    # Converte os dados da tabela para o tipo numérico
    df["radiacao_kj_m2"] = pd.to_numeric(
        df["Radiacao (KJ/m²)"],
        errors="coerce"
    )
    
    df["temperatura"] = pd.to_numeric(
        df["Temp. Ins. (C)"],
        errors="coerce"
    )

    # Ajusta formato da hora 
    df["Hora_formatada"] = (
        df["Hora (UTC)"]
        .apply(ajusta_hora)
    )

    # Une coluna data e hora e converte para datetime
    df["datetime_utc"] = pd.to_datetime(
        df["Data"] + " " + df["Hora_formatada"],
        format="%d/%m/%Y %H:%M",
        errors="coerce"
    )
    # Converte para hora loca
    df["datetime_local"] = (
        df["datetime_utc"]
        - pd.Timedelta(hours=3)
    )

    # Filtra o intervalo de tempo que deve ser considerado
    inicio = pd.Timestamp(
        f"{2017}-01-01 01:00")
    
    fim = pd.Timestamp(
        f"{2017+1}-01-01 00:00")

    df = df[
        (df["datetime_local"] >= inicio)
        &
        (df["datetime_local"] <= fim)
    ].copy()
    
    # Reseta o indice do dataframe
    df.reset_index(
        drop=True,
        inplace=True
    )

    return df


def conversoes_ajustes(df):
    
    # Converte radiação para irradiância
    df["irradiancia_W_m2"] = (
        df["radiacao_kj_m2"] * 1000
    ) / 3600
    
    # Verifica quantos NaN existem no dataframe    
    nan_antes = df[
        ["temperatura",
         "irradiancia_W_m2"]
    ].isna().sum()

    # Imputa dados onde existe NaN
    # se no meio da série interpola, se nos extremos copia o mais próximo
    df["temperatura"] = (
        df["temperatura"]
        .interpolate()
        .bfill()
        .ffill()
    )

    df["irradiancia_W_m2"] = (
        df["irradiancia_W_m2"]
        .interpolate()
        .bfill()
        .ffill()
    )

    # Substitui irradiâncias<1 por 0
    df.loc[
        df["irradiancia_W_m2"] < 1,
        "irradiancia_W_m2"
    ] = 0

    # Verifica quantos NaN existem no dataframe após as correções
    nan_depois = df[
        ["temperatura",
         "irradiancia_W_m2"]
    ].isna().sum()
    
    # Copia apenas a hora
    df["hora"] = (
        df["datetime_local"].dt.hour
    )

    #Copia apenas a data
    df["data"] = (
        df["datetime_local"].dt.date
    )
    
    # Gera relatório
    mostrar_salvar("\nEtapa de conversões e ajustes:")
    
    mostrar_salvar(f"\nNº de linhas do dataframe: {len(df)}")

    mostrar_salvar(f"\nNº de valores NaN antes: \n{nan_antes}")

    mostrar_salvar(f"\nNº de valores NaN depois: \n{nan_depois}")
    
    mostrar_salvar(
        f"\nIrradiância máxima: "
        f"{df['irradiancia_W_m2'].max():.2f} W/m²"
    )

    mostrar_salvar(
        f"Irradiância mínima: "
        f"{df['irradiancia_W_m2'].min():.2f} W/m²"
    )

    mostrar_salvar(
        f"Temperatura máxima: "
        f"{df['temperatura'].max():.2f} °C"
    )

    mostrar_salvar(
        f"Temperatura mínima: "
        f"{df['temperatura'].min():.2f} °C"
    )

    return df

#############################################################
# CALCULA HORARIO DO NASCER E POR DO SOL
def calcular_nascer_por_sol(df):

    local = LocationInfo(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        timezone=TIMEZONE
    )

    datas = sorted(df["data"].unique())

    nascer = []
    transito = []
    por = []

    for data in datas:

        # Calcula em UTC
        s = sun(
            local.observer,
            date=data,
            tzinfo="UTC"
        )

        # Converte manualmente para UTC-3 (sem horário de verão)
        nascer.append(s["sunrise"] - timedelta(hours=3))
        transito.append(s["noon"] - timedelta(hours=3))
        por.append(s["sunset"] - timedelta(hours=3))

    df_sol = pd.DataFrame({
        "data": datas,
        "sunrise": nascer,
        "transit": transito,
        "sunset": por
    })

    # Calcula hora decimal
    df_sol["hora_nascer"] = (
        df_sol["sunrise"].dt.hour +
        df_sol["sunrise"].dt.minute / 60 +
        df_sol["sunrise"].dt.second / 3600
    )

    df_sol["hora_transito"] = (
        df_sol["transit"].dt.hour +
        df_sol["transit"].dt.minute / 60 +
        df_sol["transit"].dt.second / 3600
    )

    df_sol["hora_por"] = (
        df_sol["sunset"].dt.hour +
        df_sol["sunset"].dt.minute / 60 +
        df_sol["sunset"].dt.second / 3600
    )

    # Calcula duração do dia
    df_sol["duracao_dia"] = (
        df_sol["hora_por"] -
        df_sol["hora_nascer"]
    )

    return df_sol


############################################################
# ESTATÍSTICAS DO NASCER E POR DO SOL CALCULADOS

def estatisticas_sol(df_sol):

    mostrar_salvar("\nEtapa do cálculo do nascer e por do sol:\n")

    mostrar_salvar(
        "\nIntervalo de tempo considerado:"
        f"\nInício - {df_sol['data'].min().strftime('%d/%m/%Y')}"
        f"\nFim    - {df_sol['data'].max().strftime('%d/%m/%Y')}"
    )
    
    mostrar_salvar(
        "\nHora média nascer do sol: "
        f"\n{decimal_para_hhmm(df_sol['hora_nascer'].mean())}"
    )

    mostrar_salvar(
        "\nHora média do transito (meio-dia): "
        f"\n{decimal_para_hhmm(df_sol['hora_transito'].mean())}"
    )

    mostrar_salvar(
        "\nHora média do por do sol: "
        f"\n{decimal_para_hhmm(df_sol['hora_por'].mean())}"
    )

    mostrar_salvar(
        "\nDuração média do dia: "
        f"\n{df_sol['duracao_dia'].mean():.2f} horas"
    )


############################################################
# PLOTAGEM DOS GRÁFICOS
# Curvas diárias de irradiância
def plotar_curvas(df, df_sol):
    
    plt.figure(figsize=(10,6))

    for _, grupo in df.groupby("data"):

        plt.plot(
            grupo["hora"],
            grupo["irradiancia_W_m2"],
            alpha=0.08
        )

    nascer_medio = df_sol["hora_nascer"].mean()
    por_medio = df_sol["hora_por"].mean()

    plt.axvline(
        nascer_medio,
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Nascer médio ({decimal_para_hhmm(nascer_medio)})"
    )

    plt.axvline(
        por_medio,
        color="blue",
        linestyle="--",
        linewidth=2,
        label=f"Pôr médio ({decimal_para_hhmm(por_medio)})"
    )

    plt.xlim(0,23)
    plt.grid()
    plt.xlabel("Hora")
    plt.ylabel("Irradiância (W/m²)")
    plt.title("Curvas diárias de irradiância")
    plt.legend()
    plt.savefig(cfg.DIARIAS_IRRAD,dpi=300)
    plt.show()


# Variação do horario de nascer e por do sol ao longo do ano
def plotar_nascer_por(df_sol):

    plt.figure(figsize=(12,6))

    plt.plot(
        df_sol["data"],
        df_sol["hora_nascer"],
        label="Nascer"
    )

    plt.plot(
        df_sol["data"],
        df_sol["hora_transito"],
        label="Trânsito Solar"
    )

    plt.plot(
        df_sol["data"],
        df_sol["hora_por"],
        label="Pôr"
    )

    plt.grid()
    plt.xlabel("Data")
    plt.ylabel("Hora")
    plt.title("Variação ao longo do ano")

    plt.legend()
    plt.savefig(cfg.NASCER_POR_SOL,dpi=300)
    plt.show()


# Duração do dia
def plotar_duracao_dia(df_sol):

    plt.figure(figsize=(12,6))

    plt.plot(
        df_sol["data"],
        df_sol["duracao_dia"],
        linewidth=2
    )

    plt.grid()
    plt.xlabel("Data")
    plt.ylabel("Horas")
    plt.title("Duração do dia ao longo do ano")
    plt.savefig(cfg.DURACAO_DIA, dpi=300)
    plt.show()


############################################################
# CLUSTERIZAÇÃO DAS CURVAS DE IRRADIÂNCIA UTILIZANDO
# K-MEANS

def executar_kmeans(df):
    
    mostrar_salvar("\n\nEtapa de clusterização usando K-means:")
    
    # Inicializa lista para armazenar as curvas diárias de irradiância
    curvas = []
    # Inicializa lista para armazenar as datas correspondentes a cada curva
    datas = []

    # Agrupa os dados por dia
    for data, grupo in df.groupby("data"):

        # Ordena pela hora
        grupo = grupo.sort_values("hora")
        # Extrai a curva de irradiância
        curva = grupo["irradiancia_W_m2"].values
        # Verifica se possui as 24 horas do dia
        if len(curva) != 24:
            continue
        # Armazena os valores nas listas
        curvas.append(curva)
        datas.append(data)

    # Converte a lista de curvas em uma matriz NumPy
    # As linhas são dias e as colunas horas
    X = np.array(curvas)

    # Total de curvas armazenadas
    mostrar_salvar(f"\nTotal de curvas a serem clusterizadas: {len(X)}")

    # Determina os parâmetros do K-Means
    kmeans = KMeans(
        n_clusters=N_CLUSTERS,   # Número de grupos desejados
        random_state=42,         # Garante reprodutibilidade dos resultados
        n_init=20                # Número de inicializações do algoritmo
    )

    # Realiza a clusterização
    # labels são os rótulos de cada curva
    labels = kmeans.fit_predict(X)

    # Determina os centróides de cada cluster
    centroides = kmeans.cluster_centers_

    horas = np.arange(24)

   # PLOTA CLUSTERS
    plt.figure(figsize=(12, 7))
    
    cores = ["tab:blue", "tab:orange", "tab:green",
             "tab:red", "tab:purple", "tab:brown",
             "tab:pink", "tab:olive", "tab:cyan"]
    
    for cluster in range(N_CLUSTERS):
    
        idx = np.where(labels == cluster)[0]
    
        # Plota todas as curvas do cluster
        for i in idx:
            plt.plot(
                horas,
                X[i],
                alpha=0.08,
                color=cores[cluster]
            )
    
        # Plota o centróide do cluster
        plt.plot(
            horas,
            centroides[cluster],
            color=cores[cluster],
            linewidth=4,
            label=f"Cluster {cluster+1}"
        )
    
    plt.grid()
    plt.xlabel("Hora")
    plt.ylabel("Irradiância (W/m²)")
    plt.title("Clusters das curvas diárias")
    plt.legend()
    plt.savefig(cfg.CLUSTERS, dpi=300)
    plt.show()
    
    # Plotagem dos centróides
    plt.figure(figsize=(10,6))
    for cluster in range(N_CLUSTERS):
        plt.plot(
            horas,
            centroides[cluster],
            linewidth=4,
            label=f"Cluster {cluster+1}"
        )

    plt.grid()
    plt.xlabel("Hora")
    plt.ylabel("Irradiância (W/m²)")
    plt.title("Centróides")
    plt.legend()
    plt.savefig(cfg.CENTROIDES, dpi=300)
    plt.show()

    # Estatística dos dados
    for cluster in range(N_CLUSTERS):

        idx = np.where(labels == cluster)[0]
        qtd = len(idx)
        percentual = 100 * qtd / len(X)
        centroide = centroides[cluster]
        pico = np.max(centroide)
        hora_pico = np.argmax(centroide)
        media = np.mean(centroide)

        mostrar_salvar(f"\nCluster {cluster+1}:")
        mostrar_salvar(f"\n\tNº de dias: {qtd}")
        mostrar_salvar(f"\n\tPercentual: {percentual:.2f}%")
        mostrar_salvar(f"\n\tIrradiância média: {media:.2f} W/m²")
        mostrar_salvar(f"\n\tIrradiância máxima: {pico:.2f} W/m²")
        mostrar_salvar(f"\n\tPico às {hora_pico:02d}:00")

        relatorio.append("\n\tDatas:")
        for i in idx:
            relatorio.append(f"\n\t\t{str(datas[i])}")

    return (
        centroides,
        X,
        datas,
        labels,
    )

        
############################################################
# SALVA OS DATAFRAMES
def salvar_dataframes(
        df_processado,
        df_sol,
        X,
        datas,
        labels,
        centroides,
        arquivo_saida
    ):

    # Cria cópias para não alterar os dataframes originais
    df = df_processado.copy()
    df_sol_excel = df_sol.copy()

    # Remove timezone das colunas que possuem datetime
    for dataframe in [df, df_sol_excel]:

        for col in dataframe.select_dtypes(include=["datetimetz"]).columns:
            dataframe[col] = dataframe[col].dt.tz_localize(None)

    # Salva o arquivo
    with pd.ExcelWriter(
        arquivo_saida,
        engine="openpyxl"
    ) as writer:
        
        # Dados processados
        df.to_excel(
            writer,
            sheet_name="Dados_Processados",
            index=False
        )

        # Nascer e pôr do sol
        df_sol_excel.to_excel(
            writer,
            sheet_name="Nascer_Por_Sol",
            index=False
        )

        # Resumo dos clusters
        df_clusters = pd.DataFrame({
            "data": datas,
            "cluster": labels + 1
        })

        df_clusters.to_excel(
            writer,
            sheet_name="Resumo_Clusters",
            index=False
        )

        # Clusters individuais
        horas = [
            f"{h:02d}:00"
            for h in range(24)
        ]

        for cluster in range(N_CLUSTERS):
            idx = np.where(labels == cluster)[0]
            df_cluster = pd.DataFrame(
                X[idx],
                columns=horas
            )

            df_cluster.insert(
                0,
                "data",
                np.array(datas)[idx]
            )

            df_cluster.to_excel(
                writer,
                sheet_name=f"Cluster_{cluster+1}",
                index=False
            )

        # Centróides
        df_centroides = pd.DataFrame(
            centroides,
            columns=horas
        )

        df_centroides.insert(
            0,
            "Cluster",
            [f"Cluster {i+1}" for i in range(len(centroides))]
        )

        df_centroides.to_excel(
            writer,
            sheet_name="Centroides",
            index=False
        )

        # Estatísticas dos clusters
        estatisticas = []

        for cluster in range(N_CLUSTERS):
            idx = np.where(labels == cluster)[0]
            qtd = len(idx)
            percentual = 100 * qtd / len(X)
            centroide = centroides[cluster]
            estatisticas.append({
                "Cluster": cluster + 1,
                "Nº Dias": qtd,
                "% Ocorrência": percentual,
                "Irradiância Média (W/m²)": np.mean(centroide),
                "Irradiância Máxima (W/m²)": np.max(centroide),
                "Hora do Pico": f"{np.argmax(centroide):02d}:00"
            })

        pd.DataFrame(estatisticas).to_excel(
            writer,
            sheet_name="Estatisticas_Clusters",
            index=False
        )

    mostrar_salvar(
        f"\nDataframes salvos em:\n{arquivo_saida}"
    )        
    
    
############################################################

############################################################
# EXECUÇÃO

df = carregar_dados()

df = conversoes_ajustes(df) 

df_sol = calcular_nascer_por_sol(df)

estatisticas_sol(df_sol)

plotar_curvas(df, df_sol)

plotar_nascer_por(df_sol)

plotar_duracao_dia(df_sol)

centroides, X, datas, labels = executar_kmeans(df)

salvar_dataframes(
    df,
    df_sol,
    X,
    datas,
    labels,
    centroides,
    cfg.CLIMA_PROCESSADOS
)

salvar_relatorio()