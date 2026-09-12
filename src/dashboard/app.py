"""
AgroRisk AI - Dashboard de Risco Operacional em Frotas Agricolas
FIAP + Sompo Seguros | Sprint 4 - Fase 6

Interface visual que consome a API REST (FastAPI) e apresenta o nivel de
risco por equipamento/regiao, alertas preventivos, tendencias por regiao e
tipo de operacao, a predicao do modelo de ML (score continuo + fatores) e a
trilha de auditoria. Visoes diferenciadas por persona, derivadas do papel do
usuario autenticado via JWT:
  - Operador        -> foco em 1 equipamento + alerta com os fatores que pesaram (US-01)
  - Gestor de Frota -> overview da frota, mapa, tendencias e criterios de risco (US-04, US-05)
  - Analista        -> historico auditavel de alertas + trilha de decisoes + exportacao (US-07)

Executar:  streamlit run src/dashboard/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Reaproveita a definição de faixas do domínio (fonte única do nível de risco).
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ml.features import FAIXAS_NIVEL, calcular_features, componentes_regra  # noqa: E402
from ml.recomendacao import mensagem_alerta  # noqa: E402

# --------------------------------------------------------------------------- #
# Configuracao geral
# --------------------------------------------------------------------------- #
API_BASE_URL = os.getenv("DASHBOARD_API_URL", "http://127.0.0.1:8000/api/v1")

# Teto do parâmetro `limit` aceito por GET /api/v1/telemetria (validação da issue #2).
LIMITE_HISTORICO = 1000

# Usuários semeados em `src/sql/02_seed_data.sql`, usados na demonstração e nos prints.
USUARIOS_DEMO = {
    "operador": {"nome": "Carlos", "email": "carlos@agrorisk.local", "senha": "operador123"},
    "gestor": {"nome": "Fernanda", "email": "fernanda@agrorisk.local", "senha": "gestor123"},
    "analista": {"nome": "Ricardo", "email": "ricardo@sompo.local", "senha": "analista123"},
}

CORES_RISCO = {
    "Baixo": "#2ecc71",
    "Médio": "#f1c40f",
    "Alto": "#e67e22",
    "Crítico": "#e74c3c",
}
ORDEM_RISCO = ["Baixo", "Médio", "Alto", "Crítico"]

# Nomes amigaveis (PT) para eixos e tooltips do Plotly.
ROTULOS = {
    "nivel_risco": "Nível de risco",
    "tipo_equipamento": "Tipo",
    "estado_uf": "Região",
    "score_risco": "Score de risco",
    "score_risco_predito": "Score do modelo",
    "id_equipamento": "Equipamento",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "data_hora": "Data/Hora",
    "dia": "Dia",
}

# Esconde a barra de ferramentas em ingles do Plotly e deixa em pt-BR.
PLOT_CONFIG = {"displayModeBar": False, "locale": "pt-BR"}

# Mapeamento papel -> label amigavel (para titulo da visao).
LABEL_PAPEL = {
    "Operador": "Operador",
    "GestorFrota": "Gestor de Frota",
    "AnalistaSeguradora": "Analista da Seguradora",
}

st.set_page_config(
    page_title="AgroRisk AI | Sompo",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Estilo (tema escuro moderno)
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
        .stApp { background-color: #0e1117; }
        section[data-testid="stSidebar"] { background-color: #161a23; }
        #MainMenu, footer, header { visibility: hidden; }

        .hero {
            background: linear-gradient(110deg, #e6007e 0%, #7a1fa2 55%, #2a0e4a 100%);
            padding: 1.4rem 1.8rem; border-radius: 16px; margin-bottom: 1.2rem;
        }
        .hero h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 700; }
        .hero p  { color: #f3e1ee; margin: .25rem 0 0; font-size: .95rem; }

        div[data-testid="stMetric"] {
            background: #1b2130; border: 1px solid #2a3142;
            border-radius: 14px; padding: 1rem 1.1rem;
        }
        div[data-testid="stMetricValue"] { font-size: 1.9rem; }

        .pill {
            display:inline-block; padding:.3rem 1rem; border-radius:999px;
            color:#fff; font-weight:700; font-size:1.05rem;
        }
        .legenda span {
            display:inline-block; margin-right:1rem; font-size:.85rem; color:#c8c8c8;
        }
        .dot { display:inline-block; width:11px; height:11px; border-radius:50%;
               margin-right:5px; vertical-align:middle; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Camada de dados — cliente da API
# --------------------------------------------------------------------------- #
def _auth_headers() -> dict:
    """Retorna headers com o token JWT armazenado em session_state."""
    return {"Authorization": f"Bearer {st.session_state['token']}"}


def fazer_login(email: str, senha: str) -> dict | None:
    """Autentica na API e retorna os dados do usuario + token."""
    try:
        resp = httpx.post(f"{API_BASE_URL}/login", json={"email": email, "senha": senha}, timeout=10)
    except httpx.ConnectError:
        st.error("Não foi possível conectar à API. Verifique se o servidor está rodando.")
        return None
    if resp.status_code == 401:
        st.error("Credenciais inválidas.")
        return None
    if resp.status_code != 200:
        st.error(f"Erro no login (HTTP {resp.status_code}).")
        return None
    token = resp.json()["access_token"]
    # Valida o token server-side e obtém os dados do usuário via /me (não
    # decodifica o JWT localmente — a API é a fonte de verdade do papel).
    try:
        me = httpx.get(
            f"{API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.ConnectError:
        st.error("Não foi possível validar a sessão na API.")
        return None
    if me.status_code != 200:
        st.error(f"Sessão inválida (HTTP {me.status_code}).")
        return None
    dados = me.json()
    return {
        "token": token,
        "id_usuario": dados["id_usuario"],
        "nome": dados["nome"],
        "role": dados["role"],
        "id_equipamento_acesso": dados.get("id_equipamento_acesso"),
    }


def carregar_telemetria() -> pd.DataFrame:
    """Busca o histórico de telemetria via API (GET /api/v1/telemetria).

    A API valida `limit` (1-1000 desde a issue #2): pedir acima disso devolve 422.
    """
    resp = httpx.get(
        f"{API_BASE_URL}/telemetria",
        params={"limit": LIMITE_HISTORICO},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    if df.empty:
        return df
    df["data_hora"] = pd.to_datetime(df["data_hora"], format="mixed")
    df["nivel_risco"] = pd.Categorical(df["nivel_risco"], categories=ORDEM_RISCO, ordered=True)
    return df


def carregar_equipamentos() -> pd.DataFrame:
    """Busca a lista de equipamentos via API (GET /api/v1/equipamentos)."""
    resp = httpx.get(
        f"{API_BASE_URL}/equipamentos",
        headers=_auth_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def carregar_alertas() -> pd.DataFrame:
    """Busca os alertas emitidos via API (GET /api/v1/alertas)."""
    resp = httpx.get(
        f"{API_BASE_URL}/alertas",
        headers=_auth_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def carregar_auditoria(limite: int = 200) -> pd.DataFrame:
    """Busca a trilha de auditoria via API (GET /api/v1/auditoria) — restrita a gestor/analista."""
    resp = httpx.get(
        f"{API_BASE_URL}/auditoria",
        params={"limit": min(limite, LIMITE_HISTORICO)},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], format="mixed")
    return df


def ultima_leitura_por_equipamento(df: pd.DataFrame) -> pd.DataFrame:
    """Estado atual = leitura mais recente de cada equipamento."""
    return (
        df.sort_values("data_hora")
        .groupby("id_equipamento", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def pill(nivel: str) -> str:
    cor = CORES_RISCO.get(nivel, "#888")
    return f'<span class="pill" style="background:{cor}">{nivel}</span>'


def _fatores_do_registro(registro: pd.Series) -> list[str]:
    """Fatores da predição daquele registro; registro sem predição devolve lista vazia."""
    fatores = registro.get("fatores_principais")
    return list(fatores) if isinstance(fatores, list) else []


def legenda_cores() -> None:
    itens = "".join(
        f'<span><span class="dot" style="background:{c}"></span>{n}</span>'
        for n, c in CORES_RISCO.items()
    )
    st.markdown(f'<div class="legenda">{itens}</div>', unsafe_allow_html=True)


def config_tabela_risco() -> dict:
    """column_config padrao: cabecalhos PT, score em barra, datas formatadas."""
    return {
        "Equipamento": st.column_config.TextColumn("Equipamento", width="small"),
        "Tipo": st.column_config.TextColumn("Tipo"),
        "Região": st.column_config.TextColumn("Região", width="small"),
        "Score": st.column_config.ProgressColumn(
            "Score de risco", min_value=0, max_value=100, format="%d"
        ),
        "Risco (regra)": st.column_config.TextColumn("Risco (regra)"),
        "Risco (ML)": st.column_config.TextColumn("Risco (ML)"),
        "Última leitura": st.column_config.DatetimeColumn(
            "Última leitura", format="DD/MM/YYYY HH:mm"
        ),
        "Data/Hora": st.column_config.DatetimeColumn(
            "Data/Hora", format="DD/MM/YYYY HH:mm"
        ),
        "Prox. água (m)": st.column_config.NumberColumn("Prox. água (m)", format="%d m"),
    }


# --------------------------------------------------------------------------- #
# Graficos
# --------------------------------------------------------------------------- #
def grafico_mapa(df_atual: pd.DataFrame) -> go.Figure:
    """Distribuição geográfica da frota por nível de risco.

    Usa `scatter_geo` (mapa embutido no Plotly) em vez de tiles de rua: renderiza sem
    token/rede e aparece em print e em navegador sem WebGL — `scatter_map` depende de
    tiles externos e de WebGL, que ficam em branco na captura de tela.
    """
    fig = px.scatter_geo(
        df_atual,
        lat="latitude",
        lon="longitude",
        color="nivel_risco",
        size="score_risco",
        size_max=20,
        hover_name="id_equipamento",
        hover_data={
            "tipo_equipamento": True,
            "estado_uf": True,
            "score_risco": True,
            "latitude": False,
            "longitude": False,
            "nivel_risco": True,
        },
        labels=ROTULOS,
        color_discrete_map=CORES_RISCO,
        category_orders={"nivel_risco": ORDEM_RISCO},
        projection="natural earth",
    )
    fig.update_geos(
        scope="south america",
        showcountries=True,
        countrycolor="#3b4252",
        landcolor="#1c2128",
        oceancolor="#0e1117",
        showocean=True,
        showcoastlines=True,
        coastlinecolor="#3b4252",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=460,
        legend_title_text="Nível de risco",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6",
    )
    return fig


def grafico_distribuicao(df_atual: pd.DataFrame) -> go.Figure:
    cont = df_atual["nivel_risco"].value_counts().reindex(ORDEM_RISCO, fill_value=0)
    fig = px.bar(
        x=cont.index,
        y=cont.values,
        color=cont.index,
        color_discrete_map=CORES_RISCO,
        text=cont.values,
        labels={"x": "Nível de risco", "y": "Equipamentos"},
    )
    fig.update_layout(
        showlegend=False,
        height=320,
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis_title="",
        yaxis_title="Nº de equipamentos",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6",
    )
    return fig


def grafico_evolucao(df: pd.DataFrame) -> go.Figure:
    serie = (
        df.assign(dia=df["data_hora"].dt.date)
        .groupby("dia", as_index=False)["score_risco"]
        .mean()
    )
    fig = px.area(serie, x="dia", y="score_risco", labels=ROTULOS)
    fig.update_traces(line_color="#e6007e", fillcolor="rgba(230,0,126,.18)")
    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis_title="",
        yaxis_title="Score médio de risco",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6",
    )
    return fig


# --------------------------------------------------------------------------- #
# Visoes por persona
# --------------------------------------------------------------------------- #
def grafico_tendencia_por_dimensao(df: pd.DataFrame, dimensao: str) -> go.Figure:
    """Score médio por dia, separado por região (UF) ou tipo de operação."""
    serie = df.copy()
    serie["dia"] = pd.to_datetime(serie["data_hora"]).dt.date
    agrupado = (
        serie.groupby(["dia", dimensao], as_index=False)["score_risco"].mean()
    )
    fig = px.line(
        agrupado,
        x="dia",
        y="score_risco",
        color=dimensao,
        labels={**ROTULOS, "score_risco": "Score médio"},
        markers=True,
    )
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="", yaxis_title="Score médio",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6", legend_title_text="",
    )
    return fig


def grafico_media_por_dimensao(df_atual: pd.DataFrame, dimensao: str) -> go.Figure:
    """Score médio atual por região (UF) ou por tipo de operação."""
    agrupado = (
        df_atual.groupby(dimensao, as_index=False)["score_risco"]
        .mean()
        .sort_values("score_risco", ascending=False)
    )
    fig = px.bar(
        agrupado,
        x=dimensao,
        y="score_risco",
        labels={**ROTULOS, "score_risco": "Score médio"},
        color="score_risco",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
    )
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="", yaxis_title="Score médio", coloraxis_showscale=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6",
    )
    return fig


def criterios_de_risco() -> None:
    """Mostra, de forma legível, o critério que classifica risco e dispara alerta."""
    faixas = " · ".join(
        f"**{nivel}**: {minimo}-{maximo}" for nivel, (minimo, maximo) in FAIXAS_NIVEL.items()
    )
    st.caption(
        "Critério de classificação (escala 0-100, igual para a regra e para o modelo): "
        f"{faixas}. "
        "Alerta preventivo é emitido quando o nível da **regra** é **Alto** ou **Crítico** — "
        "a regra é a fonte única de decisão (penalidades auditáveis). O modelo é **segunda "
        "opinião**: níveis divergentes (`Risco (ML)` × `Risco (regra)`) sinalizam caso ambíguo."
    )


def visao_gestor(df: pd.DataFrame) -> None:
    st.caption(
        "Visão **Gestor de Frota** — panorama de todos os equipamentos, "
        "regiões mais críticas e tendência de risco ao longo do tempo."
    )
    atual = ultima_leitura_por_equipamento(df)
    total = len(atual)
    criticos = int((atual["nivel_risco"].isin(["Alto", "Crítico"])).sum())
    score_medio = atual["score_risco"].mean() if total else 0
    pct_critico = (criticos / total * 100) if total else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equipamentos monitorados", total)
    c2.metric("Em risco Alto/Crítico", criticos, f"{pct_critico:.0f}% da frota")
    c3.metric("Score médio de risco", f"{score_medio:.1f}")
    c4.metric("Regiões ativas", atual["estado_uf"].nunique())

    st.divider()
    st.subheader("🗺️ Mapa de risco da frota")
    legenda_cores()
    st.plotly_chart(grafico_mapa(atual), use_container_width=True, config=PLOT_CONFIG)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("📊 Distribuição por nível")
        st.plotly_chart(grafico_distribuicao(atual), use_container_width=True, config=PLOT_CONFIG)
    with col_b:
        st.subheader("📈 Evolução do risco médio")
        st.plotly_chart(grafico_evolucao(df), use_container_width=True, config=PLOT_CONFIG)

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("🗺️ Tendência por região")
        st.plotly_chart(
            grafico_tendencia_por_dimensao(df, "estado_uf"), use_container_width=True, config=PLOT_CONFIG
        )
    with col_d:
        st.subheader("🚧 Score médio por tipo de operação")
        st.plotly_chart(
            grafico_media_por_dimensao(df, "tipo_operacao"), use_container_width=True, config=PLOT_CONFIG
        )

    criterios_de_risco()

    st.divider()
    st.subheader("🚜 Equipamentos da frota")
    st.caption("Ordenado pelo maior score. Compare a classificação por regra vs. a predição do modelo de ML.")
    tabela = atual[
        ["id_equipamento", "tipo_equipamento", "estado_uf", "score_risco",
         "nivel_risco", "nivel_risco_predito", "data_hora"]
    ].sort_values("score_risco", ascending=False)
    tabela = tabela.rename(
        columns={
            "id_equipamento": "Equipamento", "tipo_equipamento": "Tipo",
            "estado_uf": "Região", "score_risco": "Score",
            "nivel_risco": "Risco (regra)", "nivel_risco_predito": "Risco (ML)",
            "data_hora": "Última leitura",
        }
    )
    st.dataframe(
        tabela, use_container_width=True, hide_index=True,
        column_config=config_tabela_risco(),
    )


def visao_operador(df: pd.DataFrame) -> None:
    st.caption(
        "Visão **Operador** — situação do seu equipamento agora, com alerta "
        "e recomendação direta para a operação em campo."
    )
    equip = st.selectbox(
        "Selecione o equipamento",
        sorted(df["id_equipamento"].unique()),
        help="Escolha a máquina que você está operando.",
    )
    hist = df[df["id_equipamento"] == equip].sort_values("data_hora")
    if hist.empty:
        st.warning("Sem dados para este equipamento.")
        return
    atual = hist.iloc[-1]
    nivel = str(atual["nivel_risco"])

    st.markdown(f"### `{equip}` — {atual['tipo_equipamento']} · {atual['estado_uf']}")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    with c1:
        st.markdown("**Status atual**")
        st.markdown(pill(nivel), unsafe_allow_html=True)
    score_modelo = atual.get("score_risco_predito")
    c2.metric("Score da regra", int(atual["score_risco"]))
    c3.metric(
        f"Score do modelo ({atual.get('nivel_risco_predito') or '—'})",
        int(score_modelo) if score_modelo is not None else "—",
        delta=None if score_modelo is None else int(score_modelo) - int(atual["score_risco"]),
        delta_color="off",
        help="Mesma escala 0-100 da regra. A regra soma penalidades explícitas; o modelo "
        "pondera as probabilidades do Random Forest. Divergência grande indica caso ambíguo.",
    )

    fatores = _fatores_do_registro(atual)
    if fatores:
        st.caption("Variáveis que mais pesaram na predição do modelo: " + ", ".join(f"`{f}`" for f in fatores))

    if nivel in ("Alto", "Crítico"):
        # A REGRA decide o alerta (fonte única) e explica as penalidades que somaram o
        # score; o modelo aparece como segunda opinião — divergência é ambiguidade sinalizada.
        componentes = componentes_regra(calcular_features(atual.to_dict()))
        pred = {
            "nivel_risco_predito": atual.get("nivel_risco_predito"),
            "score_risco_predito": atual.get("score_risco_predito"),
        }
        st.error(
            f"🚨 ALERTA {nivel.upper()} para {equip}: {mensagem_alerta(nivel, componentes, pred)}"
        )
    elif nivel == "Médio":
        st.warning("⚠️ Atenção moderada. Monitore as condições do solo e do clima.")
    else:
        st.success("✅ Operação dentro de parâmetros seguros.")

    st.subheader("Condições atuais do equipamento")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Proximidade da água", f"{int(atual['proximidade_agua_m'])} m")
    g2.metric("Umidade do solo", f"{atual['umidade_solo_pct']:.0f} %")
    g3.metric("Declividade", f"{atual['declividade_graus']:.1f}°")
    g4.metric("Precipitação 24h", f"{atual['precipitacao_mm']:.1f} mm")

    st.subheader("Histórico recente de score")
    fig = px.line(hist.tail(30), x="data_hora", y="score_risco", markers=True, labels=ROTULOS)
    fig.update_traces(line_color="#e6007e")
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="", yaxis_title="Score",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6e6e6",
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
    criterios_de_risco()


def visao_analista() -> None:
    st.caption(
        "Visão **Analista da Seguradora** — histórico auditável dos alertas "
        "de risco Alto/Crítico emitidos pelo sistema, com exportação para análise de sinistros."
    )
    alertas = carregar_alertas()
    if alertas.empty:
        st.info("Nenhum alerta emitido até o momento.")
        return
    alertas = alertas.sort_values("data_hora_alerta", ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Alertas emitidos", len(alertas))
    c2.metric("Críticos", int((alertas["nivel_risco"] == "Crítico").sum()))
    c3.metric("Equipamentos afetados", alertas["id_equipamento"].nunique())

    st.divider()
    st.subheader("🧾 Histórico auditável de alertas")
    cols = ["data_hora_alerta", "id_equipamento", "nivel_risco", "score_risco", "tipo_alerta", "mensagem"]
    audit = alertas[cols].rename(
        columns={
            "data_hora_alerta": "Data/Hora", "id_equipamento": "Equipamento",
            "nivel_risco": "Risco", "score_risco": "Score",
            "tipo_alerta": "Tipo", "mensagem": "Mensagem",
        }
    )
    st.dataframe(audit, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Exportar histórico (CSV)",
        audit.to_csv(index=False).encode("utf-8"),
        file_name="historico_alertas_agrorisk.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("🔎 Trilha de auditoria")
    st.caption(
        "Quem acessou, quando e **o que o sistema decidiu** — cada telemetria processada deixa "
        "registro com score da regra, score do modelo, alerta e fatores que pesaram."
    )
    trilha = carregar_auditoria()
    if trilha.empty:
        st.info("Nenhum evento registrado.")
        return

    decisoes = trilha[trilha["acao"] == "decisao_risco"]
    t1, t2, t3 = st.columns(3)
    t1.metric("Eventos registrados", len(trilha))
    t2.metric("Decisões de risco", len(decisoes))
    t3.metric("Usuários distintos", trilha["usuario"].nunique())

    colunas = ["data_hora", "usuario", "acao", "id_equipamento", "detalhes", "ip_origem"]
    legivel = trilha[colunas].rename(
        columns={
            "data_hora": "Data/Hora", "usuario": "Usuário", "acao": "Ação",
            "id_equipamento": "Equipamento", "detalhes": "Detalhes", "ip_origem": "IP",
        }
    )
    st.dataframe(legivel, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Exportar trilha (CSV)",
        legivel.to_csv(index=False).encode("utf-8"),
        file_name="trilha_auditoria_agrorisk.csv",
        mime="text/csv",
    )


# --------------------------------------------------------------------------- #
# Tela de login
# --------------------------------------------------------------------------- #
def entrar_na_sessao(dados: dict) -> None:
    """Guarda os dados do usuário autenticado na sessão do Streamlit."""
    st.session_state["token"] = dados["token"]
    st.session_state["id_usuario"] = dados["id_usuario"]
    st.session_state["nome"] = dados["nome"]
    st.session_state["role"] = dados["role"]
    st.session_state["id_equipamento_acesso"] = dados["id_equipamento_acesso"]


def tela_login() -> None:
    """Exibe o formulário de login no sidebar e o hero na área principal.

    Com ``DASHBOARD_DEMO_LOGIN`` (operador/gestor/analista), a sessão entra direto com o
    usuário de demonstração correspondente — usado para capturar prints e gravar a
    demonstração. A autenticação continua sendo feita pela API; sem a variável, o
    formulário é o caminho normal.
    """
    demo = USUARIOS_DEMO.get(os.getenv("DASHBOARD_DEMO_LOGIN", "").strip().lower())
    if demo:
        with st.spinner(f"Entrando como {demo['nome']} (usuário de demonstração)..."):
            dados = fazer_login(demo["email"], demo["senha"])
        if dados:
            entrar_na_sessao(dados)
            st.rerun()

    st.markdown(
        """
        <div class="hero">
            <h1>🚜 AgroRisk AI — Predição de Risco Operacional</h1>
            <p>FIAP + Sompo Seguros · Da gestão reativa à preventiva em frotas agrícolas</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("Faça login para acessar o dashboard. A autenticação é feita via JWT na API.")

    st.sidebar.markdown("## 🔐 Login")
    email = st.sidebar.text_input("Email", value="", placeholder="email@agrorisk.local")
    senha = st.sidebar.text_input("Senha", value="", type="password")
    if st.sidebar.button("Entrar", use_container_width=True):
        if not email or not senha:
            st.sidebar.warning("Preencha email e senha.")
        else:
            with st.spinner("Autenticando..."):
                dados = fazer_login(email, senha)
            if dados:
                entrar_na_sessao(dados)
                st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("**Usuários de demonstração:**")
    for credencial in USUARIOS_DEMO.values():
        st.sidebar.caption(f"{credencial['nome']} · `{credencial['email']}` / `{credencial['senha']}`")


# --------------------------------------------------------------------------- #
# App principal
# --------------------------------------------------------------------------- #
def main() -> None:
    # --- Verifica autenticação ---
    if "token" not in st.session_state:
        tela_login()
        return

    role = st.session_state["role"]
    label = LABEL_PAPEL.get(role, role)

    # --- Sidebar: usuario + logout + filtros ---
    st.sidebar.markdown(f"## 👤 {label}")
    st.sidebar.caption(f"Autenticado como **{st.session_state['nome']}**")
    if st.sidebar.button("🚪 Sair"):
        for key in ("token", "id_usuario", "nome", "role", "id_equipamento_acesso"):
            st.session_state.pop(key, None)
        st.rerun()

    # --- Carrega dados da API ---
    try:
        df = carregar_telemetria()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            st.error("Sessão expirada. Faça login novamente.")
            for key in ("token", "id_usuario", "nome", "role", "id_equipamento_acesso"):
                st.session_state.pop(key, None)
            st.rerun()
        else:
            st.error(f"Erro ao carregar telemetria (HTTP {exc.response.status_code}).")
        return
    except httpx.ConnectError:
        st.error("Não foi possível conectar à API. Verifique se o servidor está rodando.")
        return

    if df.empty:
        st.warning("Nenhum registro de telemetria encontrado.")
        return

    st.markdown(
        """
        <div class="hero">
            <h1>🚜 AgroRisk AI — Predição de Risco Operacional</h1>
            <p>FIAP + Sompo Seguros · Da gestão reativa à preventiva em frotas agrícolas</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Filtros (client-side, sobre o DataFrame retornado pela API) ---
    st.sidebar.markdown("## 🔎 Filtros")
    ufs = sorted(df["estado_uf"].dropna().unique())
    tipos = sorted(df["tipo_equipamento"].dropna().unique())
    f_uf = st.sidebar.multiselect("Região (estado)", ufs, default=ufs,
                                  help="Deixe vazio para mostrar todas.")
    f_tipo = st.sidebar.multiselect("Tipo de equipamento", tipos, default=tipos)
    f_risco = st.sidebar.multiselect("Nível de risco", ORDEM_RISCO, default=ORDEM_RISCO)

    # Vazio = sem filtro (mostra tudo) — mais intuitivo que travar a tela.
    f_uf = f_uf or ufs
    f_tipo = f_tipo or tipos
    f_risco = f_risco or ORDEM_RISCO

    df_f = df[
        df["estado_uf"].isin(f_uf)
        & df["tipo_equipamento"].isin(f_tipo)
        & df["nivel_risco"].isin(f_risco)
    ]

    modelo = df["modelo_utilizado"].dropna().unique()
    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"🤖 Modelo de ML: **{modelo[0] if len(modelo) else 'n/d'}**  \n"
        f"📦 Registros no filtro: **{len(df_f)}**"
    )

    if df_f.empty:
        st.warning("Nenhum registro para os filtros selecionados.")
        return

    # --- Roteia para a visao da persona autenticada ---
    if role == "GestorFrota":
        visao_gestor(df_f)
    elif role == "Operador":
        visao_operador(df_f)
    else:
        visao_analista()


if __name__ == "__main__":
    main()