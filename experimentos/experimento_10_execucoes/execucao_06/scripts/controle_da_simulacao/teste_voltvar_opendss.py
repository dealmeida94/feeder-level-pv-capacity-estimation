#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TESTE MÍNIMO DO VOLT-VAR — ARQUITETURA PVWATTS

Objetivo
--------
Verificar o cenário de 20% de PV com controle Volt-VAr em uma única
solução do OpenDSS, utilizando a arquitetura atual:

    dados climáticos
          ↓
       PVWatts
          ↓
      PVShape.dss
          ↓
    PV_Master20_VV.dss
          ↓
       OpenDSS
          ↓
        SOLVE

IMPORTANTE
----------
Este teste NÃO executa o ano inteiro.

Ele serve para diagnosticar:
    - carregamento do PVShape;
    - quantidade de PVSystems;
    - presença do InvControl;
    - presença da VoltVarCurve;
    - convergência;
    - iterações do controlador;
    - potência ativa e reativa;
    - tensões mínima e máxima;
    - eventual existência de tensão zero.

O PVShape NÃO é mais carregado separadamente por este teste.
O cenário PV_Master20_VV.dss deve ser responsável por redirecionar
o PVShape.dss.
"""

from pathlib import Path
import math
import opendssdirect as dss


# ============================================================
# CAMINHOS
# ============================================================

# Este arquivo fica em:
# scripts/controle_da_simulacao/
#
# parents[2] = raiz do projeto
RAIZ_DIR = Path(__file__).resolve().parents[2]

MASTER = (
    RAIZ_DIR
    / "dados"
    / "inputs"
    / "carga_base"
    / "Master_sem_PV.dss"
)

# NOVA ARQUITETURA:
# o construtor gera PVShape.dss, e não mais PV_Clima.dss
PVSHAPE = (
    RAIZ_DIR
    / "dados"
    / "inputs"
    / "cenario_com_PV"
    / "PVShape.dss"
)

MASTER_VV = (
    RAIZ_DIR
    / "dados"
    / "inputs"
    / "cenario_com_PV"
    / "PV_Master20_VV.dss"
)


# ============================================================
# CABEÇALHO
# ============================================================

print("=" * 70)
print("TESTE MÍNIMO DO VOLT-VAR — ARQUITETURA PVWATTS")
print("=" * 70)

print("\nArquivos utilizados:")

for nome, arquivo in [
    ("Master base", MASTER),
    ("PVShape.dss", PVSHAPE),
    ("Master 20% VV", MASTER_VV),
]:
    print(f"\n{nome}:")
    print(f"  {arquivo}")

    if not arquivo.exists():
        raise FileNotFoundError(
            f"\nArquivo não encontrado:\n{arquivo}"
        )


# ============================================================
# VERIFICA O CONTEÚDO DO PVShape
# ============================================================

print("\n" + "-" * 70)
print("[0] Verificando PVShape.dss...")

texto_pvshape = PVSHAPE.read_text(encoding="utf-8")

if "New LoadShape.PVShape" not in texto_pvshape:
    raise RuntimeError(
        "PVShape.dss não contém a declaração New LoadShape.PVShape."
    )

# O novo PVShape deve ser produzido pelo PVWatts e ter 8760 pontos.
if "npts=8760" not in texto_pvshape.lower():
    print(
        "AVISO: não foi encontrada explicitamente a indicação npts=8760 "
        "em PVShape.dss."
    )

print("  Declaração LoadShape.PVShape encontrada.")
print("  PVShape.dss será carregado pelo cenário PV_Master20_VV.dss.")


# ============================================================
# VERIFICA SE O MASTER DO CENÁRIO REFERENCIA O PVSHAPE
# ============================================================

print("\n" + "-" * 70)
print("[0.1] Verificando referência ao PVShape no cenário 20% VV...")

texto_master_vv = MASTER_VV.read_text(encoding="utf-8")

if "PVShape.dss" not in texto_master_vv:
    raise RuntimeError(
        "PV_Master20_VV.dss não contém referência a PVShape.dss.\n"
        "O cenário deve carregar o PVShape da nova arquitetura."
    )

print("  Referência a PVShape.dss encontrada.")


# ============================================================
# LIMPA OPEN DSS
# ============================================================

print("\n" + "-" * 70)
print("[1] Limpando OpenDSS...")

dss.Basic.ClearAll()

print("OK")


# ============================================================
# COMPILA CIRCUITO BASE
# ============================================================

print("\n" + "-" * 70)
print("[2] Compilando circuito base...")

dss.Text.Command(
    f'compile "{MASTER}"'
)

print("OK")


# ============================================================
# CARREGA CENÁRIO 20% VOLT-VAR
# ============================================================

print("\n" + "-" * 70)
print("[3] Carregando PV_Master20_VV.dss...")

print(
    "  O próprio PV_Master20_VV.dss deve carregar "
    "o PVShape.dss."
)

dss.Text.Command(
    f'redirect "{MASTER_VV}"'
)

print("OK")


# ============================================================
# VERIFICA ELEMENTOS
# ============================================================

print("\n" + "-" * 70)
print("[4] Verificando elementos carregados...")


# ------------------------------------------------------------
# PVSYSTEMS
# ------------------------------------------------------------

print("\nPVSystems:")

pvs = dss.PVsystems.AllNames()

print(f"Quantidade: {len(pvs)}")

if len(pvs) == 0:
    raise RuntimeError(
        "Nenhum PVSystem foi encontrado após carregar o cenário."
    )

print("Primeiros PVSystems:")
print(pvs[:10])


# ------------------------------------------------------------
# INVCONTROL
# ------------------------------------------------------------

print("\nInvControls:")

# A instalação atual do OpenDSSDirect não expõe a interface
# dss.InvControl. Portanto, NÃO usamos dss.InvControl.AllNames()
# nem comandos ? para consultar esse objeto.
#
# O InvControl é confirmado procurando sua declaração nos arquivos
# DSS realmente carregados pelo cenário.

arquivos_dss_verificados = [
    MASTER_VV,
]

# O PV_Master20_VV.dss normalmente redireciona para
# geradoresPV_20_VV.dss. Se encontrarmos esse Redirect, verificamos
# também o arquivo de geradores.
for linha in texto_master_vv.splitlines():
    linha_limpa = linha.strip()

    if linha_limpa.lower().startswith("redirect"):
        partes = linha_limpa.split('"')

        if len(partes) >= 2:
            candidato = Path(partes[1])

            if candidato.exists():
                arquivos_dss_verificados.append(candidato)

# Também verificamos todos os arquivos DSS do diretório do cenário
# para evitar depender da forma como o Redirect foi escrito.
for candidato in sorted(
    (RAIZ_DIR / "dados" / "inputs" / "cenario_com_PV").glob("*.dss")
):
    if candidato not in arquivos_dss_verificados:
        arquivos_dss_verificados.append(candidato)

declaracoes_invcontrol = []

for arquivo in arquivos_dss_verificados:
    try:
        conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")

        for linha in conteudo.splitlines():
            if "New InvControl." in linha:
                declaracoes_invcontrol.append(
                    (arquivo, linha.strip())
                )

    except Exception:
        pass

if declaracoes_invcontrol:
    print(
        f"Declarações de InvControl encontradas: "
        f"{len(declaracoes_invcontrol)}"
    )

    for arquivo, linha in declaracoes_invcontrol:
        print(f"  Arquivo: {arquivo.name}")
        print(f"  {linha}")

else:
    print(
        "ATENÇÃO: nenhuma declaração New InvControl foi encontrada "
        "nos arquivos DSS do cenário."
    )

    print(
        "O teste continuará para o SOLVE, mas a presença do "
        "controle Volt-VAr não pôde ser confirmada."
    )

# ------------------------------------------------------------
# XYCURVES
# ------------------------------------------------------------

print("\nXYCurves:")

curvas = dss.XYCurves.AllNames()

print(f"Quantidade: {len(curvas)}")

if len(curvas) == 0:
    raise RuntimeError(
        "Nenhuma XYCurve foi encontrada."
    )

print(curvas)

if not any(str(c).lower() == "voltvarcurve" for c in curvas):
    if "New XYCurve.VoltVarCurve" in texto_master_vv:
        print(
            "VoltVarCurve confirmada pela declaração "
            "do cenário PV_Master20_VV.dss."
        )
    else:
        print(
            "AVISO: VoltVarCurve não apareceu com esse nome exato."
        )


# ============================================================
# CONFIGURAÇÃO DA SOLUÇÃO
# ============================================================

print("\n" + "-" * 70)
print("[5] Configurando solução...")

# Uma única solução.
# Não executamos QSTS/8760 horas.
dss.Text.Command(
    "set mode=snapshot"
)

# Controle estático para o teste do InvControl.
dss.Text.Command(
    "set controlmode=static"
)

print("OK")


# ============================================================
# SOLVE
# ============================================================

print("\n" + "-" * 70)
print("[6] Executando SOLVE...")

erro_solve = None

try:
    dss.Text.Command("solve")
    print("\nSOLVE executado sem exceção.")

except Exception as erro:
    erro_solve = erro

    print("\nERRO DURANTE O SOLVE:")
    print(type(erro).__name__)
    print(erro)


# ============================================================
# RESULTADO DA SOLUÇÃO
# ============================================================

print("\n" + "=" * 70)
print("RESULTADO")
print("=" * 70)

convergiu = dss.Solution.Converged()
iteracoes = dss.Solution.Iterations()

print(f"Convergiu: {convergiu}")
print(f"Iterações da solução: {iteracoes}")

if erro_solve is not None:
    print(
        "\nATENÇÃO: o OpenDSS gerou uma exceção durante o SOLVE."
    )


# ============================================================
# EVENT LOG
# ============================================================

print("\n" + "=" * 70)
print("EVENT LOG DO OPENDSS")
print("=" * 70)

try:
    log = dss.Solution.EventLog()

    if log:
        for evento in log:
            print(evento)
    else:
        print("EventLog vazio.")

except Exception as erro:
    print("Não foi possível obter o EventLog:")
    print(erro)


# ============================================================
# RESULTADOS ELÉTRICOS
# ============================================================

print("\n" + "=" * 70)
print("RESULTADOS ELÉTRICOS")
print("=" * 70)


# ------------------------------------------------------------
# POTÊNCIA TOTAL
# ------------------------------------------------------------

try:
    potencia = dss.Circuit.TotalPower()

    print(
        f"P total = {potencia[0]:.4f} kW"
    )

    print(
        f"Q total = {potencia[1]:.4f} kvar"
    )

except Exception as erro:
    print(
        "Não foi possível obter potência total:"
    )
    print(erro)


# ------------------------------------------------------------
# TENSÕES
# ------------------------------------------------------------

try:
    tensoes = dss.Circuit.AllBusMagPu()

    if not tensoes:
        print("Não foi possível obter tensões dos barramentos.")
    else:
        vmin = min(tensoes)
        vmax = max(tensoes)

        print(
            f"Vmin = {vmin:.6f} pu"
        )

        print(
            f"Vmax = {vmax:.6f} pu"
        )

        # Investigação específica da anomalia antiga:
        # Vmin = 0.0 pu
        zeros = [
            v for v in tensoes
            if math.isclose(v, 0.0, abs_tol=1e-12)
        ]

        if zeros:
            print(
                f"\nATENÇÃO: foram encontradas "
                f"{len(zeros)} tensão(ões) aproximadamente zero."
            )
            print(
                "Isso é uma pista importante e deve ser "
                "investigado antes da simulação completa."
            )
        else:
            print(
                "\nNenhuma tensão aproximadamente zero foi encontrada."
            )

except Exception as erro:
    print(
        "Não foi possível obter tensões:"
    )
    print(erro)


# ============================================================
# RESUMO FINAL
# ============================================================

print("\n" + "=" * 70)
print("RESUMO DO TESTE")
print("=" * 70)

print(f"PVSystems encontrados : {len(pvs)}")
print(f"InvControl confirmado no DSS: {bool(declaracoes_invcontrol)}")
print(f"XYCurves encontradas   : {len(curvas)}")
print(f"Convergiu              : {convergiu}")
print(f"Iterações              : {iteracoes}")

if erro_solve is None and convergiu:
    print("\nTESTE FINALIZADO COM SOLUÇÃO CONVERGENTE.")
else:
    print(
        "\nTESTE FINALIZADO, MAS A SOLUÇÃO PRECISA SER INVESTIGADA."
    )

print("=" * 70)
