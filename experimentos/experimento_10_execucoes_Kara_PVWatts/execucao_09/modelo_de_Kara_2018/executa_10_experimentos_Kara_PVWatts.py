#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Executor automático de 10 experimentos para o modelo de Kara + PVWatts.

Cada experimento é executado em uma CÓPIA ISOLADA do projeto.

Pipeline:
    1. construtor_de_cenarios_VoltVar_IEEE1547.py
    2. sincronização de Potencias_Cenarios.xlsx
    3. controlador_geral_VoltVar.py
    4. estimador_Kara_PVWatts.py

O clusterizador não é usado, pois o estimador de Kara trabalha diretamente
com P_kW, Q_kvar e o proxy PVWatts armazenado nos resultados do controlador.

Depois das 10 execuções, o script:
    - preserva os resultados individuais;
    - coleta os resultados do estimador;
    - consolida todas as execuções;
    - calcula média, desvio padrão, mínimo e máximo;
    - calcula o erro absoluto médio entre as 10 execuções;
    - salva tudo em XLSX e CSV na pasta analise_final.

IMPORTANTE
----------
O projeto original não é modificado.
Cada execução recebe uma nova distribuição aleatória de PVs.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

PROJECT_ROOT = Path(
    "/home/matheus/Documentos/BtM-PV-estimating_BKP_3/"
    "BtM-PV-estimating_A1_VoltVar"
).resolve()

EXPERIMENT_ROOT = (
    PROJECT_ROOT
    / "experimentos"
    / "experimento_10_execucoes_Kara_PVWatts"
).resolve()

N_EXECUCOES = 10

CONTINUAR_APOS_FALHA = True
RETOMAR_EXECUCAO = True


# ============================================================================
# SCRIPTS DO PIPELINE
# ============================================================================

SCRIPTS = [
    (
        1,
        "Scenario builder",
        PROJECT_ROOT
        / "scripts"
        / "construtor-de-cenarios"
        / "construtor_de_cenarios_VoltVar_IEEE1547.py",
    ),
    (
        3,
        "Simulation controller",
        PROJECT_ROOT
        / "scripts"
        / "controle_da_simulacao"
        / "controlador_geral_VoltVar.py",
    ),
    (
        4,
        "Kara + PVWatts estimator",
        PROJECT_ROOT
        / "modelo_de_Kara_2018"
        / "estimador_Kara_PVWatts.py",
    ),
]


# ============================================================================
# EXCLUSÕES DA CÓPIA
# ============================================================================

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "experimentos",
}

EXCLUDE_RELATIVE_DIRS = {
    Path("dados/outputs/cenarios_PV"),
    Path("dados/outputs/clusters"),
    Path("dados/outputs/estimacao_PV"),
    Path("figuras"),
    Path("logs"),
}


# ============================================================================
# AUXILIARES
# ============================================================================

def print_header(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def formatar_tempo(segundos):
    minutos = int(segundos // 60)
    segundos_restantes = segundos % 60
    return f"{minutos:02d}:{segundos_restantes:05.2f}"


def verificar_scripts():
    print_header("CHECKING KARA + PVWATTS PIPELINE")

    erros = []

    for numero, nome, caminho in SCRIPTS:
        if caminho.exists():
            print(f"[OK] Step {numero}: {nome}")
            print(f"     {caminho}")
        else:
            print(f"[ERROR] Step {numero}: {nome}")
            print(f"        File not found: {caminho}")
            erros.append(caminho)

    if erros:
        raise FileNotFoundError(
            "One or more pipeline scripts were not found."
        )


def deve_excluir_relativo(rel):
    if rel.name in EXCLUDE_DIRS:
        return True

    for excluido in EXCLUDE_RELATIVE_DIRS:
        if rel == excluido or excluido in rel.parents:
            return True

    return False


def copiar_projeto_isolado(destino):
    """
    Copia o projeto para uma pasta nova, excluindo resultados gerados.

    A exclusão é feita a partir do caminho RELATIVO da árvore de origem.
    Isso evita copiar resultados de uma execução anterior para a nova rodada.
    """
    print(f"\nCreating isolated workspace:")
    print(f"  {destino}")

    destino.mkdir(parents=True, exist_ok=False)

    for item in PROJECT_ROOT.iterdir():
        rel = item.relative_to(PROJECT_ROOT)

        if deve_excluir_relativo(rel):
            continue

        destino_item = destino / rel

        if item.is_dir():
            shutil.copytree(
                item,
                destino_item,
                ignore=criar_ignore_para_arvore,
            )
        else:
            if item.suffix != ".pyc" and item.name != ".DS_Store":
                destino_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destino_item)


def criar_ignore_para_arvore(directory, names):
    """
    Ignore usado pelo copytree.

    'directory' pertence à árvore de ORIGEM, portanto podemos calcular
    corretamente o caminho relativo ao projeto original.
    """
    directory = Path(directory)

    try:
        rel_dir = directory.relative_to(PROJECT_ROOT)
    except ValueError:
        return set()

    ignorados = set()

    for name in names:
        candidate = rel_dir / name

        if name in EXCLUDE_DIRS:
            ignorados.add(name)
            continue

        if name.endswith(".pyc") or name == ".DS_Store":
            ignorados.add(name)
            continue

        if deve_excluir_relativo(candidate):
            ignorados.add(name)

    return ignorados


def criar_pastas_execucao(pasta_execucao):
    (pasta_execucao / "logs").mkdir(parents=True, exist_ok=True)

    (pasta_execucao / "dados" / "outputs" / "cenarios_PV").mkdir(
        parents=True, exist_ok=True
    )

    (pasta_execucao / "dados" / "outputs" / "clusters").mkdir(
        parents=True, exist_ok=True
    )

    (pasta_execucao / "dados" / "outputs" / "estimacao_PV").mkdir(
        parents=True, exist_ok=True
    )

    (pasta_execucao / "figuras").mkdir(
        parents=True, exist_ok=True
    )


def adaptar_potencias_cenarios(pasta_execucao):
    """
    O construtor salva Potencias_Cenarios.xlsx em:
        dados/inputs/cenario_com_PV/

    O configs.py usado pelo estimador espera:
        logs/Potencias_Cenarios.xlsx
    """
    origem = (
        pasta_execucao
        / "dados"
        / "inputs"
        / "cenario_com_PV"
        / "Potencias_Cenarios.xlsx"
    )

    destino = (
        pasta_execucao
        / "logs"
        / "Potencias_Cenarios.xlsx"
    )

    if not origem.exists():
        raise FileNotFoundError(
            "Potencias_Cenarios.xlsx não foi encontrado após o construtor.\n"
            f"Esperado em: {origem}"
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)

    print()
    print("-" * 78)
    print("STEP 2/4 - Adapt execution paths")
    print("-" * 78)
    print(f"Source:      {origem}")
    print(f"Destination: {destino}")
    print("[OK] Potencias_Cenarios.xlsx synchronized.")
    print("-" * 78)


def executar_script(numero, nome, script_original, pasta_execucao):
    rel = script_original.relative_to(PROJECT_ROOT)
    script = pasta_execucao / rel

    if not script.exists():
        raise FileNotFoundError(
            f"Script not found in isolated workspace: {script}"
        )

    print()
    print("-" * 78)
    print(f"STEP {numero}/4 - {nome}")
    print(f"Script: {script}")
    print("-" * 78)

    log_path = (
        pasta_execucao
        / "logs"
        / f"{numero:02d}_{script.stem}.log"
    )

    inicio = time.perf_counter()

    with log_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as log:

        log.write("=" * 78 + "\n")
        log.write(f"STEP {numero}: {nome}\n")
        log.write(f"Script: {script}\n")
        log.write(
            f"Started: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        log.write("=" * 78 + "\n\n")

        processo = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    tempo = time.perf_counter() - inicio

    if processo.returncode != 0:
        print(f"[FAILED] Step {numero}: {nome}")
        print(f"         Return code: {processo.returncode}")
        print(f"         Log: {log_path}")

        raise RuntimeError(
            f"Step {numero} failed with return code "
            f"{processo.returncode}."
        )

    print(f"[OK] Step {numero}: {nome}")
    print(f"     Time: {formatar_tempo(tempo)}")
    print(f"     Log: {log_path}")

    return tempo


# ============================================================================
# COLETA DOS RESULTADOS DE KARA
# ============================================================================

def localizar_resultados_kara(pasta_execucao):
    """
    Localiza a planilha produzida pelo estimador de Kara.

    O estimador atual grava:
        modelo_de_Kara_2018/Resultados_Kara_PVWatts_FP1_VoltVar.xlsx
    """
    pasta_kara = pasta_execucao / "modelo_de_Kara_2018"

    candidatos = [
        pasta_kara / "Resultados_Kara_PVWatts_FP1_VoltVar.xlsx",
        pasta_kara / "Resumo_Kara_PVWatts.xlsx",
    ]

    for arquivo in candidatos:
        if arquivo.exists() and arquivo.name.startswith(
            "Resultados_Kara_PVWatts"
        ):
            return arquivo

    encontrados = list(
        pasta_kara.glob("Resultados_Kara_PVWatts*.xlsx")
    )

    if encontrados:
        return encontrados[0]

    raise FileNotFoundError(
        "Planilha de resultados do Kara não encontrada.\n"
        f"Pasta procurada: {pasta_kara}"
    )


def ler_resultados_kara(pasta_execucao, numero):
    arquivo = localizar_resultados_kara(pasta_execucao)

    df = pd.read_excel(arquivo)

    df["Execucao"] = numero
    df["Arquivo_origem"] = str(arquivo)

    return df


# ============================================================================
# EXECUÇÃO INDIVIDUAL
# ============================================================================

def executar_experimento(numero):
    nome_execucao = f"execucao_{numero:02d}"
    pasta_execucao = EXPERIMENT_ROOT / nome_execucao

    done_flag = pasta_execucao / "DONE.flag"
    failed_flag = pasta_execucao / "FAILED.flag"

    if RETOMAR_EXECUCAO and done_flag.exists():
        print(f"\n[SKIP] {nome_execucao} already completed.")
        return True

    if pasta_execucao.exists():
        print(f"\n[WARNING] {pasta_execucao} already exists.")
        print("Removing incomplete previous execution...")
        shutil.rmtree(pasta_execucao)

    inicio = time.perf_counter()

    print_header(
        f"EXPERIMENT {numero:02d}/{N_EXECUCOES}"
    )

    try:
        copiar_projeto_isolado(pasta_execucao)
        criar_pastas_execucao(pasta_execucao)

        tempos = []

        # Step 1: construtor
        numero_etapa, nome, script = SCRIPTS[0]
        tempo = executar_script(
            numero_etapa,
            nome,
            script,
            pasta_execucao,
        )
        tempos.append((numero_etapa, nome, tempo))

        # Step 2: sincronização
        inicio_adaptacao = time.perf_counter()
        adaptar_potencias_cenarios(pasta_execucao)
        tempo_adaptacao = time.perf_counter() - inicio_adaptacao
        tempos.append((2, "Adapt execution paths", tempo_adaptacao))

        # Step 3 e 4: controlador + Kara
        for numero_etapa, nome, script in SCRIPTS[1:]:
            tempo = executar_script(
                numero_etapa,
                nome,
                script,
                pasta_execucao,
            )
            tempos.append((numero_etapa, nome, tempo))

        # Verifica que o resultado do Kara realmente existe.
        arquivo_kara = localizar_resultados_kara(pasta_execucao)

        tempo_total = time.perf_counter() - inicio

        done_flag.write_text(
            "\n".join([
                "STATUS=SUCCESS",
                f"EXECUTION={numero:02d}",
                f"FINISHED={datetime.now().isoformat(timespec='seconds')}",
                f"RESULT_FILE={arquivo_kara}",
                f"TOTAL_SECONDS={tempo_total:.3f}",
            ]) + "\n",
            encoding="utf-8",
        )

        if failed_flag.exists():
            failed_flag.unlink()

        print_header(
            f"EXPERIMENT {numero:02d} COMPLETED"
        )

        print(f"Total time: {formatar_tempo(tempo_total)}")

        for etapa, nome, tempo in tempos:
            print(
                f"  Step {etapa}: "
                f"{nome:<30} "
                f"{formatar_tempo(tempo)}"
            )

        print(f"  Kara results: {arquivo_kara}")

        return True

    except Exception as exc:
        tempo_total = time.perf_counter() - inicio

        failed_flag.write_text(
            "\n".join([
                "STATUS=FAILED",
                f"EXECUTION={numero:02d}",
                f"FAILED_AT={datetime.now().isoformat(timespec='seconds')}",
                f"TOTAL_SECONDS={tempo_total:.3f}",
                f"ERROR={repr(exc)}",
            ]) + "\n",
            encoding="utf-8",
        )

        print_header(
            f"EXPERIMENT {numero:02d} FAILED"
        )

        print(f"Error: {exc}")
        print("Workspace preserved at:")
        print(f"  {pasta_execucao}")

        return False


# ============================================================================
# CONSOLIDAÇÃO
# ============================================================================

def consolidar_resultados(resultados_execucoes):
    """
    Consolida os resultados de Kara das execuções bem-sucedidas.

    Mantém cada observação individual e calcula estatísticas agrupadas por:
        Cenario + Janela + VoltVar
    """
    print_header("CONSOLIDATING KARA RESULTS")

    frames = []

    for numero, sucesso in resultados_execucoes:
        if not sucesso:
            continue

        pasta_execucao = EXPERIMENT_ROOT / f"execucao_{numero:02d}"

        try:
            df = ler_resultados_kara(
                pasta_execucao,
                numero,
            )
            frames.append(df)
            print(
                f"[OK] Execution {numero:02d}: "
                f"{len(df)} Kara result rows"
            )
        except Exception as exc:
            print(
                f"[WARNING] Could not collect execution "
                f"{numero:02d}: {exc}"
            )

    if not frames:
        print("No Kara results available for consolidation.")
        return

    todos = pd.concat(
        frames,
        ignore_index=True,
    )

    pasta_analise = EXPERIMENT_ROOT / "analise_final"
    pasta_analise.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Salva todas as observações das 10 execuções.
    arquivo_todos = (
        pasta_analise
        / "Resultados_Kara_PVWatts_todas_execucoes.xlsx"
    )
    todos.to_excel(
        arquivo_todos,
        index=False,
    )

    arquivo_todos_csv = (
        pasta_analise
        / "Resultados_Kara_PVWatts_todas_execucoes.csv"
    )
    todos.to_csv(
        arquivo_todos_csv,
        index=False,
    )

    # Colunas esperadas pelo estimador atual.
    colunas_grupo = [
        "Cenario",
        "Janela",
        "VoltVar",
    ]

    coluna_erro = "Erro_percentual"

    # Se os nomes tiverem mudado, não inventamos uma estatística.
    if not all(c in todos.columns for c in colunas_grupo):
        print(
            "\n[WARNING] Columns for grouped analysis not found:"
        )
        print(f"Required: {colunas_grupo}")
        return

    if coluna_erro not in todos.columns:
        print(
            f"\n[WARNING] Column '{coluna_erro}' not found. "
            "Grouped error statistics will not be calculated."
        )
        return

    agregacoes = {
        coluna_erro: [
            "mean",
            "std",
            "min",
            "max",
        ],
        "Potencia_estimada_kW": [
            "mean",
            "std",
            "min",
            "max",
        ],
        "Potencia_real_kW": [
            "mean",
        ],
    }

    resumo = (
        todos
        .groupby(colunas_grupo, dropna=False)
        .agg(agregacoes)
        .reset_index()
    )

    # Achata MultiIndex das colunas.
    novas_colunas = []

    for coluna in resumo.columns:
        if isinstance(coluna, tuple):
            partes = [
                str(parte)
                for parte in coluna
                if str(parte) != ""
            ]
            novas_colunas.append("_".join(partes))
        else:
            novas_colunas.append(str(coluna))

    resumo.columns = novas_colunas

    # Renomes amigáveis.
    resumo = resumo.rename(
        columns={
            f"{coluna_erro}_mean": "Erro_medio_percentual",
            f"{coluna_erro}_std": "Desvio_padrao_erro_percentual",
            f"{coluna_erro}_min": "Erro_minimo_percentual",
            f"{coluna_erro}_max": "Erro_maximo_percentual",
            "Potencia_estimada_kW_mean": "Potencia_estimada_media_kW",
            "Potencia_estimada_kW_std": "Desvio_padrao_estimativa_kW",
            "Potencia_estimada_kW_min": "Potencia_estimada_min_kW",
            "Potencia_estimada_kW_max": "Potencia_estimada_max_kW",
            "Potencia_real_kW_mean": "Potencia_real_kW",
        }
    )

    # Erro absoluto médio entre as execuções.
    erro_abs = (
        todos
        .groupby(colunas_grupo, dropna=False)[coluna_erro]
        .apply(lambda s: s.abs().mean())
        .reset_index(name="Erro_absoluto_medio_percentual")
    )

    resumo = resumo.merge(
        erro_abs,
        on=colunas_grupo,
        how="left",
    )

    arquivo_resumo = (
        pasta_analise
        / "Media_Resultados_Kara_PVWatts_10_execucoes.xlsx"
    )

    resumo.to_excel(
        arquivo_resumo,
        index=False,
    )

    arquivo_resumo_csv = (
        pasta_analise
        / "Media_Resultados_Kara_PVWatts_10_execucoes.csv"
    )

    resumo.to_csv(
        arquivo_resumo_csv,
        index=False,
    )

    # Relatório textual simples.
    arquivo_txt = pasta_analise / "Resumo_10_execucoes_Kara.txt"

    with arquivo_txt.open(
        "w",
        encoding="utf-8",
    ) as f:
        f.write("KARA + PVWATTS - 10 EXECUCOES\n")
        f.write("=" * 70 + "\n\n")
        f.write(
            f"Execuções coletadas: "
            f"{todos['Execucao'].nunique()}\n"
        )
        f.write(
            f"Linhas de resultados: "
            f"{len(todos)}\n\n"
        )

        f.write(
            "MÉDIAS POR CENÁRIO / JANELA / AMBIENTE\n"
        )
        f.write("-" * 70 + "\n")

        f.write(
            resumo.to_string(index=False)
        )
        f.write("\n")

    print()
    print("Consolidated files:")
    print(f"  All executions XLSX:")
    print(f"    {arquivo_todos}")
    print(f"  All executions CSV:")
    print(f"    {arquivo_todos_csv}")
    print(f"  Mean/statistics XLSX:")
    print(f"    {arquivo_resumo}")
    print(f"  Mean/statistics CSV:")
    print(f"    {arquivo_resumo_csv}")
    print(f"  Text summary:")
    print(f"    {arquivo_txt}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    inicio_total = time.perf_counter()

    print_header(
        "BtM-PV-estimating - KARA + PVWATTS - "
        "AUTOMATED 10-EXPERIMENT RUNNER"
    )

    print("Original project:")
    print(f"  {PROJECT_ROOT}")

    print("\nExperiment directory:")
    print(f"  {EXPERIMENT_ROOT}")

    print("\nNumber of experiments:")
    print(f"  {N_EXECUCOES}")

    print(
        "\nThe original project will NOT be modified."
    )

    print(
        "\nEach execution will create a new PV distribution "
        "through the scenario builder."
    )

    print(
        "\nPipeline:"
        "\n  1. Scenario builder"
        "\n  2. Potencias_Cenarios synchronization"
        "\n  3. Simulation controller"
        "\n  4. Kara + PVWatts estimator"
    )

    if not PROJECT_ROOT.exists():
        raise FileNotFoundError(
            f"Project directory not found:\n{PROJECT_ROOT}"
        )

    verificar_scripts()

    EXPERIMENT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    resultados = []

    for numero in range(1, N_EXECUCOES + 1):
        sucesso = executar_experimento(numero)

        resultados.append(
            (numero, sucesso)
        )

        if not sucesso and not CONTINUAR_APOS_FALHA:
            print(
                "\nStopping because CONTINUAR_APOS_FALHA=False."
            )
            break

    consolidar_resultados(resultados)

    tempo_total = time.perf_counter() - inicio_total

    print_header(
        "FINAL EXPERIMENT SUMMARY"
    )

    sucessos = 0
    falhas = 0

    for numero, sucesso in resultados:
        if sucesso:
            status = "SUCCESS"
            sucessos += 1
        else:
            status = "FAILED"
            falhas += 1

        print(
            f"Experiment {numero:02d}: {status}"
        )

    print()
    print(f"Successful experiments: {sucessos}")
    print(f"Failed experiments:     {falhas}")
    print(
        f"Total elapsed time:     "
        f"{formatar_tempo(tempo_total)}"
    )

    print()
    print("Results are isolated under:")
    print(f"  {EXPERIMENT_ROOT}")

    resumo_execucoes = (
        EXPERIMENT_ROOT
        / "experiment_summary.csv"
    )

    with resumo_execucoes.open(
        "w",
        encoding="utf-8",
    ) as f:
        f.write("experiment,status\n")

        for numero, sucesso in resultados:
            f.write(
                f"{numero:02d},"
                f"{'SUCCESS' if sucesso else 'FAILED'}\n"
            )

    print()
    print("Execution summary:")
    print(f"  {resumo_execucoes}")


if __name__ == "__main__":
    main()
