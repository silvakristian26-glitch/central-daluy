# Central de Atendimento Daluy
# Protótipo: reúne os vários números de WhatsApp da empresa numa única tela,
# com cadastro de clientes, controle de demandas, painel e IA.
#
# Como rodar:
#   uv venv
#   uv pip install -r requirements.txt
#   .venv\Scripts\streamlit.exe run app.py

import sqlite3
from datetime import datetime, timedelta, date

import pandas as pd
import plotly.express as px
import streamlit as st

BANCO = "daluy.db"
STATUS = ["Aberta", "Em andamento", "Concluída"]
PRIORIDADES = ["Baixa", "Média", "Alta"]

st.set_page_config(page_title="Central Daluy", page_icon="💬", layout="wide")


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def conectar():
    conexao = sqlite3.connect(BANCO, check_same_thread=False)
    conexao.row_factory = sqlite3.Row
    return conexao


def criar_tabelas():
    with conectar() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                empresa TEXT,
                numero_whatsapp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                direcao TEXT NOT NULL CHECK (direcao IN ('recebida', 'enviada')),
                texto TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                lida INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                titulo TEXT NOT NULL,
                descricao TEXT,
                responsavel TEXT,
                status TEXT NOT NULL DEFAULT 'Aberta',
                prioridade TEXT NOT NULL DEFAULT 'Média',
                prazo TEXT,
                criada_em TEXT NOT NULL
            );
            """
        )


def popular_dados_exemplo():
    """Cria clientes, conversas e demandas fictícias na primeira execução."""
    with conectar() as con:
        if con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] > 0:
            return

        clientes = [
            ("Mariana Costa", "Padaria Pão Dourado", "(61) 99811-2034"),
            ("Ricardo Alves", "Alves Construções", "(61) 99234-7781"),
            ("Juliana Rocha", "Clínica Bem Estar", "(61) 98456-1290"),
            ("Fernando Lima", "Lima Transportes", "(61) 99678-4402"),
        ]
        con.executemany(
            "INSERT INTO clientes (nome, empresa, numero_whatsapp) VALUES (?, ?, ?)",
            clientes,
        )

        agora = datetime.now()
        conversas = {
            1: [
                ("recebida", "Bom dia! Preciso do relatório de vendas do mês passado.", 50),
                ("enviada", "Bom dia, Mariana! Vou preparar e te envio ainda hoje.", 48),
                ("recebida", "Ótimo. Consegue incluir a comparação com o mês anterior?", 30),
            ],
            2: [
                ("recebida", "Olá, a nota fiscal do serviço de setembro ainda não chegou.", 26),
                ("enviada", "Olá, Ricardo. Vou verificar com o financeiro.", 25),
                ("recebida", "Por favor, preciso dela até sexta para fechar o caixa.", 3),
            ],
            3: [
                ("recebida", "Oi! Podemos marcar uma reunião para revisar o contrato?", 20),
                ("enviada", "Claro, Juliana. Quinta às 10h funciona?", 19),
                ("recebida", "Funciona sim, obrigada!", 18),
            ],
            4: [
                ("recebida", "Boa tarde, a planilha de entregas está com valores errados na aba de outubro.", 2),
            ],
        }
        for cliente_id, msgs in conversas.items():
            for direcao, texto, horas_atras in msgs:
                momento = agora - timedelta(hours=horas_atras)
                lida = 1 if horas_atras > 10 else 0
                con.execute(
                    "INSERT INTO mensagens (cliente_id, direcao, texto, data_hora, lida) VALUES (?, ?, ?, ?, ?)",
                    (cliente_id, direcao, texto, momento.isoformat(timespec="seconds"), lida),
                )

        hoje = date.today()
        demandas = [
            (1, "Relatório de vendas mensal", "Incluir comparação com o mês anterior.", "Daluy", "Em andamento", "Alta", hoje + timedelta(days=1)),
            (2, "Enviar NF de setembro", "Cliente precisa até sexta.", "Financeiro", "Aberta", "Alta", hoje + timedelta(days=3)),
            (3, "Reunião de revisão de contrato", "Quinta às 10h.", "Daluy", "Concluída", "Média", hoje - timedelta(days=1)),
            (4, "Corrigir planilha de entregas", "Valores errados na aba de outubro.", "Daluy", "Aberta", "Média", hoje + timedelta(days=5)),
        ]
        for c_id, titulo, desc, resp, status, prio, prazo in demandas:
            con.execute(
                """INSERT INTO demandas (cliente_id, titulo, descricao, responsavel, status, prioridade, prazo, criada_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (c_id, titulo, desc, resp, status, prio, prazo.isoformat(), agora.isoformat(timespec="seconds")),
            )


def consulta(sql, parametros=()):
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=parametros)


def executar(sql, parametros=()):
    with conectar() as con:
        con.execute(sql, parametros)


# ---------------------------------------------------------------------------
# Inteligência Artificial (opcional)
# Usa a mesma chave do Google AI Studio do chatbot, guardada em
# .streamlit/secrets.toml  ->  API_KEY = "sua-chave"
# ---------------------------------------------------------------------------
def obter_cliente_ia():
    try:
        chave = st.secrets["API_KEY"]
    except Exception:
        return None
    from openai import OpenAI

    return OpenAI(api_key=chave, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")


def perguntar_ia(instrucao, conversa_texto):
    cliente_ia = obter_cliente_ia()
    if cliente_ia is None:
        return None
    try:
        modelo = st.secrets.get("MODELO", "gemini-2.5-flash")
    except Exception:
        modelo = "gemini-2.5-flash"
    resposta = cliente_ia.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": "Você é assistente de atendimento de uma empresa brasileira. Responda em português, de forma curta e profissional."},
            {"role": "user", "content": f"{instrucao}\n\nConversa:\n{conversa_texto}"},
        ],
    )
    return resposta.choices[0].message.content


def conversa_como_texto(mensagens):
    linhas = []
    for _, m in mensagens.iterrows():
        quem = "Cliente" if m["direcao"] == "recebida" else "Empresa"
        linhas.append(f"{quem}: {m['texto']}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
def tela_caixa_entrada():
    st.header("💬 Caixa de entrada unificada")
    st.caption("Todas as conversas de todos os números de WhatsApp em um só lugar.")

    lista = consulta(
        """
        SELECT c.id, c.nome, c.empresa, c.numero_whatsapp,
               MAX(m.data_hora) AS ultima,
               SUM(CASE WHEN m.lida = 0 AND m.direcao = 'recebida' THEN 1 ELSE 0 END) AS nao_lidas
        FROM clientes c
        LEFT JOIN mensagens m ON m.cliente_id = c.id
        GROUP BY c.id
        ORDER BY ultima DESC
        """
    )
    if lista.empty:
        st.info("Nenhum cliente cadastrado. Cadastre na tela Clientes.")
        return

    col_lista, col_chat = st.columns([1, 2.2])

    with col_lista:
        busca = st.text_input("🔎 Buscar cliente", placeholder="Nome ou empresa")
        if busca:
            filtro = lista["nome"].str.contains(busca, case=False) | lista["empresa"].fillna("").str.contains(busca, case=False)
            lista = lista[filtro]

        if "cliente_aberto" not in st.session_state and not lista.empty:
            st.session_state["cliente_aberto"] = int(lista.iloc[0]["id"])

        for _, c in lista.iterrows():
            nao_lidas = int(c["nao_lidas"] or 0)
            selo = f"  🔴 {nao_lidas}" if nao_lidas else ""
            rotulo = f"**{c['nome']}**{selo}\n\n{c['empresa'] or ''} · {c['numero_whatsapp']}"
            tipo = "primary" if st.session_state.get("cliente_aberto") == c["id"] else "secondary"
            if st.button(rotulo, key=f"cli_{c['id']}", width="stretch", type=tipo):
                st.session_state["cliente_aberto"] = int(c["id"])
                st.session_state.pop("resultado_ia", None)
                st.rerun()

    cliente_id = st.session_state.get("cliente_aberto")
    if cliente_id is None:
        return

    cliente = consulta("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).iloc[0]
    executar("UPDATE mensagens SET lida = 1 WHERE cliente_id = ? AND direcao = 'recebida'", (cliente_id,))
    mensagens = consulta("SELECT * FROM mensagens WHERE cliente_id = ? ORDER BY data_hora", (cliente_id,))

    with col_chat:
        st.subheader(f"{cliente['nome']} — {cliente['empresa'] or ''}")
        st.caption(f"📱 Número: {cliente['numero_whatsapp']}")

        with st.container(height=380):
            for _, m in mensagens.iterrows():
                papel = "user" if m["direcao"] == "recebida" else "assistant"
                avatar = "👤" if papel == "user" else "🏢"
                hora = datetime.fromisoformat(m["data_hora"]).strftime("%d/%m %H:%M")
                st.chat_message(papel, avatar=avatar).write(f"{m['texto']}  \n:gray[{hora}]")

        resposta = st.chat_input("Escreva a resposta para o cliente...")
        if resposta:
            executar(
                "INSERT INTO mensagens (cliente_id, direcao, texto, data_hora, lida) VALUES (?, 'enviada', ?, ?, 1)",
                (cliente_id, resposta, datetime.now().isoformat(timespec="seconds")),
            )
            st.rerun()

        b1, b2, b3 = st.columns(3)
        texto = conversa_como_texto(mensagens)
        if b1.button("✨ Resumir conversa", width="stretch"):
            st.session_state["resultado_ia"] = ("Resumo", perguntar_ia("Resuma esta conversa em até 3 tópicos e diga o que o cliente está pedindo.", texto))
        if b2.button("✨ Sugerir resposta", width="stretch"):
            st.session_state["resultado_ia"] = ("Sugestão de resposta", perguntar_ia("Sugira uma resposta educada para a última mensagem do cliente.", texto))
        if b3.button("📌 Criar demanda", width="stretch"):
            st.session_state["nova_demanda_cliente"] = cliente_id

        if "resultado_ia" in st.session_state:
            titulo, conteudo = st.session_state["resultado_ia"]
            if conteudo is None:
                st.warning("IA não configurada. Crie o arquivo .streamlit/secrets.toml com API_KEY = \"sua-chave\".")
            else:
                st.info(f"**{titulo}:**\n\n{conteudo}")

        if st.session_state.get("nova_demanda_cliente") == cliente_id:
            with st.form("form_demanda_chat", clear_on_submit=True):
                st.markdown("**Nova demanda a partir desta conversa**")
                titulo = st.text_input("Título")
                descricao = st.text_area("Descrição", value=mensagens.iloc[-1]["texto"] if not mensagens.empty else "")
                c1, c2, c3 = st.columns(3)
                responsavel = c1.text_input("Responsável", value="Daluy")
                prioridade = c2.selectbox("Prioridade", PRIORIDADES, index=1)
                prazo = c3.date_input("Prazo", value=date.today() + timedelta(days=3), format="DD/MM/YYYY")
                if st.form_submit_button("Salvar demanda"):
                    if titulo.strip():
                        salvar_demanda(cliente_id, titulo, descricao, responsavel, prioridade, prazo)
                        st.session_state.pop("nova_demanda_cliente")
                        st.success("Demanda criada!")
                        st.rerun()
                    else:
                        st.error("Informe o título.")

        with st.expander("🧪 Simular mensagem recebida (para demonstração)"):
            simulada = st.text_input("Texto que o cliente enviou", key="simulada")
            if st.button("Receber mensagem") and simulada:
                executar(
                    "INSERT INTO mensagens (cliente_id, direcao, texto, data_hora, lida) VALUES (?, 'recebida', ?, ?, 0)",
                    (cliente_id, simulada, datetime.now().isoformat(timespec="seconds")),
                )
                st.rerun()


def salvar_demanda(cliente_id, titulo, descricao, responsavel, prioridade, prazo):
    executar(
        """INSERT INTO demandas (cliente_id, titulo, descricao, responsavel, status, prioridade, prazo, criada_em)
           VALUES (?, ?, ?, ?, 'Aberta', ?, ?, ?)""",
        (cliente_id, titulo.strip(), descricao, responsavel, prioridade, prazo.isoformat(), datetime.now().isoformat(timespec="seconds")),
    )


def tela_demandas():
    st.header("📋 Demandas")
    clientes = consulta("SELECT id, nome FROM clientes ORDER BY nome")

    with st.expander("➕ Nova demanda"):
        with st.form("form_demanda", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome_cliente = c1.selectbox("Cliente", clientes["nome"])
            titulo = c2.text_input("Título")
            descricao = st.text_area("Descrição")
            c3, c4, c5 = st.columns(3)
            responsavel = c3.text_input("Responsável", value="Daluy")
            prioridade = c4.selectbox("Prioridade", PRIORIDADES, index=1)
            prazo = c5.date_input("Prazo", value=date.today() + timedelta(days=3), format="DD/MM/YYYY")
            if st.form_submit_button("Salvar"):
                if titulo.strip() and nome_cliente:
                    cliente_id = int(clientes.loc[clientes["nome"] == nome_cliente, "id"].iloc[0])
                    salvar_demanda(cliente_id, titulo, descricao, responsavel, prioridade, prazo)
                    st.success("Demanda cadastrada!")
                    st.rerun()
                else:
                    st.error("Preencha cliente e título.")

    demandas = consulta(
        """SELECT d.id, c.nome AS cliente, d.titulo, d.descricao, d.responsavel,
                  d.status, d.prioridade, d.prazo
           FROM demandas d JOIN clientes c ON c.id = d.cliente_id
           ORDER BY d.prazo"""
    )
    if demandas.empty:
        st.info("Nenhuma demanda cadastrada.")
        return

    f1, f2, f3 = st.columns(3)
    filtro_status = f1.multiselect("Status", STATUS, default=["Aberta", "Em andamento"])
    filtro_cliente = f2.multiselect("Cliente", sorted(demandas["cliente"].unique()))
    filtro_prio = f3.multiselect("Prioridade", PRIORIDADES)

    if filtro_status:
        demandas = demandas[demandas["status"].isin(filtro_status)]
    if filtro_cliente:
        demandas = demandas[demandas["cliente"].isin(filtro_cliente)]
    if filtro_prio:
        demandas = demandas[demandas["prioridade"].isin(filtro_prio)]

    demandas["prazo"] = pd.to_datetime(demandas["prazo"]).dt.date
    hoje = date.today()
    demandas["situação"] = demandas.apply(
        lambda d: "⚠️ Atrasada" if d["status"] != "Concluída" and d["prazo"] < hoje else "", axis=1
    )

    st.caption("Altere o status direto na tabela e clique em Salvar alterações.")
    editado = st.data_editor(
        demandas,
        hide_index=True,
        width="stretch",
        disabled=["id", "cliente", "titulo", "descricao", "responsavel", "prioridade", "prazo", "situação"],
        column_config={
            "status": st.column_config.SelectboxColumn("status", options=STATUS),
            "prazo": st.column_config.DateColumn("prazo", format="DD/MM/YYYY"),
        },
        key="editor_demandas",
    )
    if st.button("💾 Salvar alterações"):
        for _, linha in editado.iterrows():
            executar("UPDATE demandas SET status = ? WHERE id = ?", (linha["status"], int(linha["id"])))
        st.success("Status atualizados!")
        st.rerun()


def tela_clientes():
    st.header("👥 Clientes")
    with st.form("form_cliente", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome do contato")
        empresa = c2.text_input("Empresa")
        numero = c3.text_input("Número de WhatsApp", placeholder="(61) 99999-9999")
        if st.form_submit_button("Cadastrar cliente"):
            if nome.strip() and numero.strip():
                executar(
                    "INSERT INTO clientes (nome, empresa, numero_whatsapp) VALUES (?, ?, ?)",
                    (nome.strip(), empresa.strip(), numero.strip()),
                )
                st.success("Cliente cadastrado!")
                st.rerun()
            else:
                st.error("Nome e número são obrigatórios.")

    clientes = consulta(
        """SELECT c.nome, c.empresa, c.numero_whatsapp,
                  (SELECT COUNT(*) FROM demandas d WHERE d.cliente_id = c.id AND d.status != 'Concluída') AS demandas_abertas
           FROM clientes c ORDER BY c.nome"""
    )
    st.dataframe(clientes, hide_index=True, width="stretch")


def tela_painel():
    st.header("📊 Painel de demandas")
    demandas = consulta(
        """SELECT d.*, c.nome AS cliente FROM demandas d JOIN clientes c ON c.id = d.cliente_id"""
    )
    mensagens = consulta("SELECT * FROM mensagens")

    hoje = date.today().isoformat()
    abertas = demandas[demandas["status"] != "Concluída"]
    atrasadas = abertas[abertas["prazo"] < hoje]
    nao_lidas = mensagens[(mensagens["lida"] == 0) & (mensagens["direcao"] == "recebida")]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Demandas em aberto", len(abertas))
    m2.metric("Atrasadas", len(atrasadas))
    m3.metric("Concluídas", int((demandas["status"] == "Concluída").sum()))
    m4.metric("Mensagens não lidas", len(nao_lidas))

    if demandas.empty:
        st.info("Sem dados para exibir.")
        return

    g1, g2 = st.columns(2)
    por_status = demandas.groupby("status").size().reindex(STATUS, fill_value=0).reset_index(name="quantidade")
    g1.plotly_chart(px.bar(por_status, x="status", y="quantidade", title="Demandas por status"), width="stretch")

    por_cliente = abertas.groupby("cliente").size().reset_index(name="quantidade")
    if not por_cliente.empty:
        g2.plotly_chart(px.bar(por_cliente, x="cliente", y="quantidade", title="Demandas em aberto por cliente"), width="stretch")

    if not mensagens.empty:
        mensagens["dia"] = pd.to_datetime(mensagens["data_hora"]).dt.date
        por_dia = mensagens.groupby(["dia", "direcao"]).size().reset_index(name="quantidade")
        st.plotly_chart(px.bar(por_dia, x="dia", y="quantidade", color="direcao", barmode="group",
                               title="Mensagens por dia"), width="stretch")

    st.subheader("Exportar para o Power BI / Excel")
    st.download_button(
        "⬇️ Baixar demandas (CSV)",
        demandas.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="demandas_daluy.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
criar_tabelas()
popular_dados_exemplo()

st.sidebar.title("💬 Central Daluy")
st.sidebar.caption("Atendimento unificado de WhatsApp")
tela = st.sidebar.radio("Menu", ["Caixa de entrada", "Demandas", "Clientes", "Painel"])

if tela == "Caixa de entrada":
    tela_caixa_entrada()
elif tela == "Demandas":
    tela_demandas()
elif tela == "Clientes":
    tela_clientes()
else:
    tela_painel()
