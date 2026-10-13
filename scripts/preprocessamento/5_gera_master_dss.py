'''
Gera um arquivo Master.dss baseado no arquivo Master.dss original
'''

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))

import configs as cfg


# Elementos do sistema que constam no Master.dss original
elementos_sistema = {
    "Vsource.dss"            : "Source definition",
    "SubTransformer.dss"     : "Substation transformer definition",
    "RegControl.dss"         : "Tap changer control definition",
    "DistriTransformer.dss"  : "Secondary distribution transformer definition",
    "Linecode.dss"           : "Line configuration",
    "Line.dss"               : "Line segment definition",
    "CircuitBreaker.dss"     : "Circuit breaker definition",
    "Capacitor.dss"          : "Shunt capacitor bank definition"
}

################################################################################
######  FUNÇÃO PARA LISTAR OS ARQUIVOS .dss CONTIDOS EM UMA PASTA  #############
#
# local: diretório onde será feita a busca
# filtrar_nome: verifica se a string informada existe no nome do arquivo
# se não for informado, assume None e não aplica filtro
#
# retorna uma lista com os caminhos completos de cada arquivo encontrado
def listar_arquivos(local, filtrar_nome = None):
    arquivos = []

    if not os.path.exists(local):
        return arquivos

    for f in sorted(os.listdir(local)):
        if f.endswith(".dss"):
            if filtrar_nome:
                if filtrar_nome.lower() not in f.lower():
                    continue
            caminho = os.path.join(local, f)
            arquivos.append(caminho)
    return arquivos

################################################################################
########  FUNÇÃO PARA CRIAR UM DICIONARIO ASSOCIANDO NOME:LOCAL  ###############
def criadic_nome_local(lista_arquivos):
    dic = {}
    for caminho in lista_arquivos:
        nome = os.path.basename(caminho)
        dic[nome] = caminho
    return dic

################################################################################
#################  FUNÇÕES GERA REDIRECTS PARA OS ARQUIVOS  ####################
def gerar_redirects_simples(lista_arquivos):
    redirects = []
    erros = []

    for arq in lista_arquivos:
        if os.path.exists(arq):
            redirects.append(f'Redirect "{arq}"\n')
        else:
            erros.append(f"Arquivo não encontrado: {arq}")

    return redirects, erros


def gerar_redirects_compostos(lista_arquivos):
    elemento_nome = criadic_nome_local(lista_arquivos)
    redirects = []
    erros = []
    
    for nome, comentario in elementos_sistema.items():
        if nome in elemento_nome:
            caminho = elemento_nome[nome]
            raiz = f'Redirect "{caminho}"'
            raiz_ajustada = raiz.ljust(100)
            redirects.append(f'{raiz_ajustada}! {comentario}\n')
        else:
            erros.append(f"Arquivo {nome} não encontrado!")

    return redirects, erros

################################################################################
######################## GERA O ARQUIVO MASTER.dss #############################

# Produz as listas com os caminhos para os arquivos
elementos = listar_arquivos(cfg.ELEM_DIR)
loadshapes = listar_arquivos(cfg.BASE_LOAD, filtrar_nome="Loadshapes")
loads = listar_arquivos(cfg.BASE_LOAD, filtrar_nome='Loads')

# Inicialização
novo_conteudo = []
log_erros = []

# Validação do Buscoords (AGORA CORRETA)
buscoords_caminho = cfg.ELEM_DIR / "Buscoords.dss"
if not os.path.exists(buscoords_caminho):
    log_erros.append("Arquivo Buscoords.dss não encontrado.")

#=========================================================================
# ESTRUTURA DO ARQUIVO
# Cabeçalho
novo_conteudo.append("// This is the OpenDSS Master file to solve the test system time-series power flow using loadshapes.\n\n")
novo_conteudo.append("Clear\n")
novo_conteudo.append("New Circuit.240_bus_test_system   ! Initiate a new circuit\n\n\n")

# ELEMENTOS DO SISTEMA
novo_conteudo.append("! ELEMENTOS DO SISTEMA\n")
novo_conteudo.append("!--------------------------------------------------------!\n")
redirects_elementos, erros = gerar_redirects_compostos(elementos)
novo_conteudo.extend(redirects_elementos)
log_erros.extend(erros)

# LOADSHAPES
novo_conteudo.append("\n\n\n! ==============================\n")
novo_conteudo.append("! LOADSHAPES\n")
novo_conteudo.append("! ==============================\n")
redirects_ls, erros_ls = gerar_redirects_simples(loadshapes)
novo_conteudo.extend(redirects_ls)
log_erros.extend(erros_ls)

# LOADS
novo_conteudo.append("\n\n\n! ==============================\n")
novo_conteudo.append("! LOADS\n")
novo_conteudo.append("! ==============================\n")
redirects_ld, erros_ld = gerar_redirects_simples(loads)
novo_conteudo.extend(redirects_ld)
log_erros.extend(erros_ld)

# PARÂMETROS
novo_conteudo.append("\n\n\n!--------------------------Calculate---------------------!\n")
novo_conteudo.append('Set VoltageBases = "69.0, 13.8, 0.208"\n')
novo_conteudo.append("CalcVoltageBases\n") 
novo_conteudo.append("solve\n")

# BUSCOORDS
novo_conteudo.append(f'BusCoords "{buscoords_caminho}"\n\n')

#=========================================================================
# FIM DO ARQUIVO

# Salva relatório
with open(cfg.LOG_MASTER, "w") as log:
    if log_erros:
        log.write("Elementos não encontrados:\n")
        for erro in log_erros:
            log.write(erro + "\n")
    else:
        log.write("Todos os arquivos foram encontrados. Nenhum erro.\n")

# Print relatório
if log_erros:
    print("\nERRO !!!:\n")
    for erro in log_erros:
        print(erro)
    print("\nArquivo 'Master_sem_PV.dss' não foi gerado.")

else:
    with open(cfg.BASE_LOAD / "Master_sem_PV.dss", "w") as f:
        f.writelines(novo_conteudo)
    print("\nTodos os elementos da rede foram encontrados.\n")
    print(f"O arquivo 'Master_sem_PV.dss' foi salvo em: {cfg.BASE_LOAD}")