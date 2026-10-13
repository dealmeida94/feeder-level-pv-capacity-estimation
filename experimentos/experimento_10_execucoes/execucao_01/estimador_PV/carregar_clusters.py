import pandas as pd

def carregar_clusters(lista_clusters):

    dados_clusters = {}

    for item in lista_clusters:

        cenario = item["cenario"]
        cluster = item["cluster"]

        df = pd.read_parquet(item["arquivo"])

        if cenario not in dados_clusters:
            dados_clusters[cenario] = {}

        # Cria DataFrame
        dados_clusters[cenario][cluster] = df

    print(
        f"\nForam carregados os dados dos clusters de "
        f"{len(dados_clusters)} cenários."
    )

    for cenario, clusters in dados_clusters.items():

        print(
            f"Cenário {cenario}%: "
            f"{len(clusters)} clusters"
        )

    return dados_clusters