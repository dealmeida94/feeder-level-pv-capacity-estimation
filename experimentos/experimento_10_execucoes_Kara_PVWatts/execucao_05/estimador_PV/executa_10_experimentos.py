#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Executor automático de experimentos BtM-PV-estimating - Volt-VAr

Executa, em sequência, N experimentos independentes:

1. construtor_de_cenarios_VoltVar_IEEE1547.py
2. sincronização de Potencias_Cenarios.xlsx
3. controlador_geral_VoltVar.py
4. clusterizador_FP1_VoltVar.py
5. main_estimar_PV_FP1_VoltVar.py
6. analisar_resultados.py

IMPORTANTE
----------
- Os arquivos do projeto original NÃO são modificados.
- Cada execução ocorre em uma cópia isolada do projeto.
- Cada execução possui sua própria árvore de resultados.
- Se uma etapa falhar, a execução é marcada como FAILED e o experimento
  seguinte pode continuar (configurável).
- Os logs stdout/stderr de cada script são salvos em logs/.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

PROJECT_ROOT = Path(
    "/home/matheus/Documentos/BtM-PV-estimating_BKP_3/"
    "BtM-PV-estimating_A1_VoltVar"
).resolve()

# Pasta completamente separada do projeto original.
EXPERIMENT_ROOT = (
    PROJECT_ROOT
    / "experimentos"
    / "experimento_10_execucoes"
).resolve()

N_EXECUCOES = 10

# True = continua para a próxima execução se uma execução falhar.
CONTINUAR_APOS_FALHA = True

# True = pula uma execução que já possui DONE.flag.
# Isso permite interromper e continuar depois.
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
        "Clusterization",
        PROJECT_ROOT
        / "estimador_PV"
        / "clusterizador_FP1_VoltVar.py",
    ),
    (
        5,
        "PV estimation",
        PROJECT_ROOT
        / "estimador_PV"
        / "main_estimar_PV_FP1_VoltVar.py",
    ),
    (
        6,
        "Result analysis",
        PROJECT_ROOT
        / "estimador_PV"
        / "analisar_resultados.py",
    ),
]


# ============================================================================
# DIRETÓRIOS GERADOS QUE NÃO DEVEM SER COPIADOS DO PROJETO ORIGINAL
# ============================================================================

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "experimentos",
}

# Esses diretórios são gerados/modificados pelo pipeline.
# Não os copiamos do projeto original para dentro do experimento.
EXCLUDE_RELATIVE_DIRS = {
    Path("dados/outputs/cenarios_PV"),
    Path("dados/outputs/clusters"),
    Path("dados/outputs/estimacao_PV"),
    Path("figuras"),
    Path("logs"),
}


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def print_header(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def verificar_scripts():
    """Verifica se os seis itens do pipeline existem no projeto original."""
    print_header("CHECKING PIPELINE SCRIPTS")

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


def caminho_relativo(caminho):
    return caminho.relative_to(PROJECT_ROOT)


def deve_excluir_diretorio(path):
    """Decide se um diretório deve ser excluído da cópia."""
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        return False

    if rel.name in EXCLUDE_DIRS:
        return True

    for excluido in EXCLUDE_RELATIVE_DIRS:
        if rel == excluido or excluido in rel.parents:
            return True

    return False


def deve_excluir_arquivo(path):
    """Evita arquivos temporários/caches."""
    if path.name.endswith(".pyc"):
        return True

    if path.name == ".DS_Store":
        return True

    return False


def copiar_projeto_isolado(destino):
    """
    Cria uma cópia do projeto original sem copiar os diretórios de resultados
    gerados pelo pipeline.

    A cópia mantém a mesma estrutura relativa do projeto, portanto os
    configs.py que calculam RAIZ_DIR a partir de __file__ continuam apontando
    para a cópia, e não para o projeto original.
    """

    print(f"\nCreating isolated workspace:")
    print(f"  {destino}")

    destino.mkdir(parents=True, exist_ok=False)

    for item in PROJECT_ROOT.iterdir():

        if item.name in EXCLUDE_DIRS:
            continue

        destino_item = destino / item.name

        if item.is_dir():

            # Caminho relativo do item em relação ao projeto original.
            rel = item.relative_to(PROJECT_ROOT)

            # Exclui árvores geradas.
            if rel in EXCLUDE_RELATIVE_DIRS:
                continue

            # Se estiver dentro de uma árvore excluída, não copia.
            if any(
                rel == exc or exc in rel.parents
                for exc in EXCLUDE_RELATIVE_DIRS
            ):
                continue

            shutil.copytree(
                item,
                destino_item,
                ignore=ignorar_arvore
            )

        elif item.is_file():

            if not deve_excluir_arquivo(item):
                shutil.copy2(item, destino_item)


def ignorar_arvore(directory, names):
    """
    Função de ignore usada pelo copytree.

    directory é um diretório da cópia que está sendo criada.
    """
    directory = Path(directory)

    ignorados = set()

    try:
        rel_dir = directory.relative_to(PROJECT_ROOT)
    except ValueError:
        rel_dir = Path()

    for name in names:
        candidate_rel = rel_dir / name

        if name in EXCLUDE_DIRS:
            ignorados.add(name)
            continue

        if name.endswith(".pyc"):
            ignorados.add(name)
            continue

        for exc in EXCLUDE_RELATIVE_DIRS:
            if candidate_rel == exc or exc in candidate_rel.parents:
                ignorados.add(name)
                break

    return ignorados


def criar_pastas_execucao(pasta_execucao):
    """Cria as pastas adicionais usadas pelo executor."""
    (pasta_execucao / "logs").mkdir(parents=True, exist_ok=True)

    # Diretórios que os scripts atuais usam para resultados.
    (pasta_execucao / "dados" / "outputs" / "cenarios_PV").mkdir(
        parents=True,
        exist_ok=True
    )

    (pasta_execucao / "dados" / "outputs" / "clusters").mkdir(
        parents=True,
        exist_ok=True
    )

    (pasta_execucao / "dados" / "outputs" / "estimacao_PV").mkdir(
        parents=True,
        exist_ok=True
    )

    (pasta_execucao / "figuras").mkdir(
        parents=True,
        exist_ok=True
    )

    (pasta_execucao / "logs").mkdir(
        parents=True,
        exist_ok=True
    )


def adaptar_potencias_cenarios(pasta_execucao):
    """
    Sincroniza o arquivo Potencias_Cenarios.xlsx gerado pelo construtor
    com o caminho utilizado pelo estimador.

    O construtor salva em:
        dados/inputs/cenario_com_PV/Potencias_Cenarios.xlsx

    O configs.py utilizado pelo estimador espera em:
        logs/Potencias_Cenarios.xlsx

    A cópia é feita diretamente pelo executor, sem criar um script
    intermediário dentro do projeto experimental.
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
    print("STEP 2/6 - Adapt execution paths")
    print("-" * 78)
    print(f"Source:      {origem}")
    print(f"Destination: {destino}")
    print("[OK] Potencias_Cenarios.xlsx synchronized.")
    print("-" * 78)


def executar_script(numero, nome, script_original, pasta_execucao):
    """
    Executa um script usando o Python atual.

    O script é localizado pelo caminho relativo ao projeto original,
    mas executado dentro da cópia isolada.
    """

    rel = script_original.relative_to(PROJECT_ROOT)
    script = pasta_execucao / rel

    if not script.exists():
        raise FileNotFoundError(
            f"Script not found in isolated workspace: {script}"
        )

    print()
    print("-" * 78)
    print(f"STEP {numero}/6 - {nome}")
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
        errors="replace"
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


def formatar_tempo(segundos):
    minutos = int(segundos // 60)
    segundos_restantes = segundos % 60
    return f"{minutos:02d}:{segundos_restantes:05.2f}"


def executar_experimento(numero):
    """
    Executa os cinco passos de uma rodada completamente isolada.
    """

    nome_execucao = f"execucao_{numero:02d}"
    pasta_execucao = EXPERIMENT_ROOT / nome_execucao

    done_flag = pasta_execucao / "DONE.flag"
    failed_flag = pasta_execucao / "FAILED.flag"

    if RETOMAR_EXECUCAO and done_flag.exists():
        print(
            f"\n[SKIP] {nome_execucao} already completed."
        )
        return True

    if pasta_execucao.exists():
        print(
            f"\n[WARNING] {pasta_execucao} already exists."
        )
        print(
            "Removing incomplete previous execution..."
        )
        shutil.rmtree(pasta_execucao)

    inicio = time.perf_counter()

    print_header(
        f"EXPERIMENT {numero:02d}/{N_EXECUCOES}"
    )

    try:

        copiar_projeto_isolado(
            pasta_execucao
        )

        criar_pastas_execucao(
            pasta_execucao
        )

        tempos = []

        for numero_etapa, nome, script in SCRIPTS:

            # O construtor (Step 1) precisa rodar ANTES da sincronização
            # do Potencias_Cenarios.xlsx (Step 2).
            tempo = executar_script(
                numero_etapa,
                nome,
                script,
                pasta_execucao
            )

            tempos.append(
                (numero_etapa, nome, tempo)
            )

            if numero_etapa == 1:
                inicio_adaptacao = time.perf_counter()
                adaptar_potencias_cenarios(pasta_execucao)
                tempo_adaptacao = time.perf_counter() - inicio_adaptacao
                tempos.append(
                    (2, "Adapt execution paths", tempo_adaptacao)
                )

        tempo_total = time.perf_counter() - inicio

        # Registro simples da execução concluída.
        done_flag.write_text(
            "\n".join([
                "STATUS=SUCCESS",
                f"EXECUTION={numero:02d}",
                f"FINISHED={datetime.now().isoformat(timespec='seconds')}",
                f"TOTAL_SECONDS={tempo_total:.3f}",
            ]) + "\n",
            encoding="utf-8"
        )

        if failed_flag.exists():
            failed_flag.unlink()

        print_header(
            f"EXPERIMENT {numero:02d} COMPLETED"
        )

        print(
            f"Total time: {formatar_tempo(tempo_total)}"
        )

        for etapa, nome, tempo in tempos:
            print(
                f"  Step {etapa}: "
                f"{nome:<24} "
                f"{formatar_tempo(tempo)}"
            )

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
            encoding="utf-8"
        )

        print_header(
            f"EXPERIMENT {numero:02d} FAILED"
        )

        print(f"Error: {exc}")
        print(f"Workspace preserved at:")
        print(f"  {pasta_execucao}")

        return False


# ============================================================================
# MAIN
# ============================================================================

def main():

    inicio_total = time.perf_counter()

    print_header(
        "BtM-PV-estimating - AUTOMATED 10-EXPERIMENT RUNNER"
    )

    print(f"Original project:")
    print(f"  {PROJECT_ROOT}")

    print(f"\nExperiment directory:")
    print(f"  {EXPERIMENT_ROOT}")

    print(f"\nNumber of experiments:")
    print(f"  {N_EXECUCOES}")

    print(
        "\nThe original project will NOT be modified."
    )

    if not PROJECT_ROOT.exists():
        raise FileNotFoundError(
            f"Project directory not found:\n{PROJECT_ROOT}"
        )

    verificar_scripts()

    EXPERIMENT_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    resultados = []

    for numero in range(1, N_EXECUCOES + 1):

        sucesso = executar_experimento(
            numero
        )

        resultados.append(
            (numero, sucesso)
        )

        if not sucesso and not CONTINUAR_APOS_FALHA:
            print(
                "\nStopping because CONTINUAR_APOS_FALHA=False."
            )
            break

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

    # Resumo CSV simples, sem depender de pandas.
    resumo = EXPERIMENT_ROOT / "experiment_summary.csv"

    with resumo.open(
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "experiment,status\n"
        )

        for numero, sucesso in resultados:
            f.write(
                f"{numero:02d},"
                f"{'SUCCESS' if sucesso else 'FAILED'}\n"
            )

    print()
    print(f"Summary file:")
    print(f"  {resumo}")


if __name__ == "__main__":
    main()
