import streamlit as st
import pandas as pd
from io import BytesIO
import plotly.express as px
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from models import EmployeeCreate, EmployeeUpdate
from supabase_client import (
    sign_in,
    sign_up,
    sign_out,
    list_schools,
    list_employees,
    create_employee,
    update_employee,
    delete_employee,
)

# ====== CONFIGURAÇÃO DE ADMIN ======
ADMIN_EMAILS = {
    "monitoramento.conae@gmail.com",  # <- coloque aqui os e-mails admin
}

TZ_BR = ZoneInfo("America/Sao_Paulo")

def format_br_datetime(dt_str: str) -> str:
    """
    Converte string ISO (UTC) vinda do Supabase para data/hora em Brasília.
    Formato exibido: dd/mm/aaaa HH:MM
    """
    if not dt_str:
        return ""
    try:
        # Supabase geralmente retorna '2025-11-30T17:47:29.210272+00:00'
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_br = dt.astimezone(TZ_BR)
        return dt_br.strftime("%d/%m/%Y %H:%M")
    except Exception:
        # Se algo der errado, devolve o original
        return dt_str


# Wrapper para funcionar em versões novas/antigas do Streamlit
def rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


st.set_page_config(page_title="Supervisão de Funcionários", layout="wide")

BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "assets" / "artemis_logo.png"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False


def do_logout():
    """Efetua logout e limpa o estado da sessão."""
    sign_out()
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.is_admin = False
    rerun()


def render_sidebar_header():
    """Logo + info de usuário na barra lateral."""
    # Logo na sidebar
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), use_container_width=True)

    # Info de usuário + botão sair
    if st.session_state.logged_in:
        if st.session_state.is_admin:
            st.sidebar.write(f"Logado como (ADMIN): **{st.session_state.user_email}**")
        else:
            st.sidebar.write(f"Logado como: **{st.session_state.user_email}**")

        if st.sidebar.button("Sair"):
            do_logout()


# ------------------ TELAS ------------------


def show_auth_screen():
    """Tela com abas de Login e Criar conta."""

    # Logo centralizado (menor)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=260)

    # Título centralizado
    st.markdown(
        "<h1 style='text-align:center;'>Supervisão de Funcionários - Autenticação</h1>",
        unsafe_allow_html=True,
    )

    tab_login, tab_signup = st.tabs(["Login", "Criar conta"])

    # ----- LOGIN -----
    with tab_login:
        st.subheader("Entrar")

        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")

        if submitted:
            email_clean = email.strip().lower()
            if not email_clean or not password:
                st.error("Preencha e-mail e senha.")
            else:
                try:
                    resp = sign_in(email_clean, password)
                    user = resp["user"]
                    if user is None:
                        st.error("Credenciais inválidas ou e-mail não confirmado.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user.email
                        st.session_state.is_admin = user.email in ADMIN_EMAILS
                        st.success("Login realizado com sucesso.")
                        rerun()
                except Exception as e:
                    st.error(f"Erro ao fazer login: {e}")

    # ----- CRIAR CONTA -----
    with tab_signup:
        st.subheader("Criar nova conta (supervisor)")

        with st.form("signup_form"):
            email_new = st.text_input("E-mail (novo supervisor)")
            password_new = st.text_input("Senha", type="password")
            password_confirm = st.text_input("Confirmar senha", type="password")
            submitted_signup = st.form_submit_button("Criar conta")

        if submitted_signup:
            email_new_clean = email_new.strip().lower()
            if not email_new_clean or not password_new or not password_confirm:
                st.error("Preencha todos os campos.")
            elif password_new != password_confirm:
                st.error("As senhas não conferem.")
            elif len(password_new) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            else:
                try:
                    resp = sign_up(email_new_clean, password_new)
                    user = resp["user"]
                    if user is None:
                        st.warning(
                            "Conta criada, mas pode ser necessário confirmar o e-mail "
                            "no Supabase, dependendo da configuração."
                        )
                    else:
                        st.success("Conta criada com sucesso! Agora faça login na aba 'Login'.")
                except Exception as e:
                    st.error(f"Erro ao criar conta: {e}")


def show_employees_screen():
    """Tela principal de supervisão de funcionários (apenas dados do usuário)."""
    render_sidebar_header()

    st.title("Supervisão de Funcionários")

    # Carregar escolas
    try:
        schools = list_schools()
    except Exception as e:
        st.error(f"Erro ao carregar escolas: {e}")
        return

    if not schools:
        st.warning("Nenhuma escola cadastrada. Cadastre escolas direto no Supabase (tabela 'schools').")
        return

    # id -> nome
    school_map = {s.id: s.name for s in schools}
    # label visível = só o nome
    school_labels = {s.name: s.id for s in schools}

    # ---------- FORM NOVO FUNCIONÁRIO ----------
    st.subheader("Cadastrar novo funcionário")

    with st.form("new_employee_form", clear_on_submit=True):
        name = st.text_input("Nome do funcionário", max_chars=200)
        cpf = st.text_input("CPF (somente números ou com pontuação)", max_chars=14)
        selected_school_label = st.selectbox("Escola", list(school_labels.keys()))
        status = st.selectbox("Situação", ["Trabalhando", "Abandono"])
        submitted = st.form_submit_button("Cadastrar")

    if submitted:
        name_clean = name.strip()
        cpf_clean = cpf.strip()
        school_id = school_labels[selected_school_label]

        if not name_clean or not cpf_clean:
            st.warning("Nome e CPF são obrigatórios.")
        else:
            try:
                create_employee(
                    EmployeeCreate(
                        name=name_clean,
                        cpf=cpf_clean,
                        school_id=school_id,
                        status=status,
                    )
                )
                st.success("Funcionário cadastrado com sucesso.")
                rerun()
            except Exception as e:
                st.error(f"Erro ao cadastrar funcionário: {e}")

    st.markdown("---")

    # ---------- LISTA DE FUNCIONÁRIOS (APENAS DO USUÁRIO) ----------
    st.subheader("Funcionários cadastrados por você")

    try:
        employees = list_employees()
    except Exception as e:
        st.error(f"Erro ao carregar funcionários: {e}")
        return

    if not employees:
        st.info("Nenhum funcionário cadastrado ainda.")
        return

    # Se for admin, RLS traz todos. Aqui filtramos para mostrar só os dele.
    if st.session_state.is_admin:
        user_email = st.session_state.user_email
        employees = [e for e in employees if e.user_email == user_email]

    if not employees:
        st.info("Nenhum funcionário cadastrado por você.")
        return

    # Filtros locais (nome/CPF/escola) com base nos seus funcionários
    with st.expander("Filtros", expanded=False):
        filter_name = st.text_input("Filtrar por nome")
        filter_cpf = st.text_input("Filtrar por CPF")
        school_filter_options = ["Todas"] + list(school_labels.keys())
        school_filter_label = st.selectbox("Filtrar por escola", school_filter_options, index=0)

    employees_filtered = employees

    if filter_name:
        name_lower = filter_name.strip().lower()
        employees_filtered = [e for e in employees_filtered if name_lower in e.name.lower()]

    if filter_cpf:
        cpf_digits_filter = "".join(ch for ch in filter_cpf if ch.isdigit())
        employees_filtered = [
            e
            for e in employees_filtered
            if cpf_digits_filter in "".join(ch for ch in e.cpf if ch.isdigit())
        ]

    if school_filter_label != "Todas":
        school_id_filter = school_labels[school_filter_label]
        employees_filtered = [e for e in employees_filtered if e.school_id == school_id_filter]

    if not employees_filtered:
        st.info("Nenhum funcionário encontrado com os filtros aplicados.")
        return

    total = len(employees_filtered)
    trabalhando = sum(1 for e in employees_filtered if e.status == "Trabalhando")
    abandono = sum(1 for e in employees_filtered if e.status == "Abandono")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total (com filtros)", total)
    col_b.metric("Trabalhando", trabalhando)
    col_c.metric("Abandono", abandono)

    # Exportar apenas os dados desse supervisor filtrados
    df = pd.DataFrame(
        [
            {
                "Nome": e.name,
                "CPF": e.cpf,
                "Escola": school_map.get(e.school_id, f"ID {e.school_id}"),
                "Situação": e.status,
                "Cadastrado em (Brasília)": format_br_datetime(e.created_at),
                "Atualizado em (Brasília)": format_br_datetime(e.updated_at),
            }
            for e in employees_filtered
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Funcionarios")
    output.seek(0)

    st.download_button(
        label="📥 Baixar dados em Excel (seus funcionários filtrados)",
        data=output,
        file_name="funcionarios_supervisor.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("---")

    # Listagem detalhada + ações
    for emp in employees_filtered:
        with st.container():
            cols = st.columns([0.35, 0.2, 0.2, 0.1, 0.15])

            with cols[0]:
                st.markdown(f"**{emp.name}**")
                st.caption(f"CPF: {emp.cpf}")
                st.caption(f"Escola: {school_map.get(emp.school_id, f'ID {emp.school_id}')}")
                st.caption(f"Cadastrado em: {format_br_datetime(emp.created_at)}")
                st.caption(f"Atualizado em: {format_br_datetime(emp.updated_at)}")

            with cols[1]:
                status_badge = "🟢 Trabalhando" if emp.status == "Trabalhando" else "🔴 Abandono"
                st.markdown(f"**Situação:** {status_badge}")

            with cols[2]:
                toggle_label = "Marcar Abandono" if emp.status == "Trabalhando" else "Marcar Trabalhando"
                if st.button(toggle_label, key=f"toggle_{emp.id}"):
                    new_status = "Abandono" if emp.status == "Trabalhando" else "Trabalhando"
                    try:
                        update_employee(str(emp.id), EmployeeUpdate(status=new_status))
                        rerun()
                    except Exception as e:
                        st.error(f"Erro ao alterar situação: {e}")

            with cols[3]:
                if st.button("Editar", key=f"edit_{emp.id}"):
                    st.session_state[f"editing_{emp.id}"] = True
                    rerun()

            with cols[4]:
                if st.button("Excluir", key=f"delete_{emp.id}"):
                    try:
                        delete_employee(str(emp.id))
                        rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir funcionário: {e}")

            if st.session_state.get(f"editing_{emp.id}", False):
                st.markdown("**Editar funcionário**")
                with st.form(f"edit_form_{emp.id}"):
                    new_name = st.text_input("Nome", value=emp.name)
                    new_cpf = st.text_input("CPF", value=emp.cpf)
                    edit_school_label = st.selectbox(
                        "Escola",
                        list(school_labels.keys()),
                        index=list(school_labels.values()).index(emp.school_id),
                    )
                    new_status = st.selectbox(
                        "Situação",
                        ["Trabalhando", "Abandono"],
                        index=0 if emp.status == "Trabalhando" else 1,
                    )
                    col_save, col_cancel = st.columns(2)
                    save_clicked = col_save.form_submit_button("Salvar")
                    cancel_clicked = col_cancel.form_submit_button("Cancelar")

                if save_clicked:
                    try:
                        update_employee(
                            str(emp.id),
                            EmployeeUpdate(
                                name=new_name.strip() or emp.name,
                                cpf=new_cpf.strip() or emp.cpf,
                                school_id=school_labels[edit_school_label],
                                status=new_status,
                            ),
                        )
                        st.session_state[f"editing_{emp.id}"] = False
                        rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar edição: {e}")

                if cancel_clicked:
                    st.session_state[f"editing_{emp.id}"] = False
                    rerun()


def show_admin_dashboard():
    """Dashboard para usuário admin: vê todos os funcionários de todos supervisores."""
    render_sidebar_header()
    st.title("Dashboard Administrativo - Todos os Funcionários")

    try:
        schools = list_schools()
        school_map = {s.id: s.name for s in schools}
    except Exception:
        school_map = {}

    try:
        employees = list_employees()  # RLS libera todos para admin
    except Exception as e:
        st.error(f"Erro ao carregar funcionários: {e}")
        return

    if not employees:
        st.info("Nenhum funcionário cadastrado ainda.")
        return

    df = pd.DataFrame(
        [
            {
                "Nome": e.name,
                "CPF": e.cpf,
                "Escola": school_map.get(e.school_id, f"ID {e.school_id}"),
                "Situação": e.status,
                "Supervisor": e.user_email,
                "Cadastrado em (Brasília)": format_br_datetime(e.created_at),
                "Atualizado em (Brasília)": format_br_datetime(e.updated_at),
            }
            for e in employees
        ]
    )

    # Métricas gerais
    total = len(df)
    total_supervisores = df["Supervisor"].nunique()
    total_escolas = df["Escola"].nunique()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de funcionários", total)
    col2.metric("Supervisores ativos", total_supervisores)
    col3.metric("Escolas", total_escolas)

    st.markdown("---")

    # ----- GRÁFICOS EM PIZZA LADO A LADO -----
    colg1, colg2, colg3 = st.columns(3)

    # Funcionários por situação
    with colg1:
        st.subheader("Por situação")
        sit_counts = df["Situação"].value_counts().reset_index()
        sit_counts.columns = ["Situação", "Quantidade"]
        fig_sit = px.pie(
            sit_counts,
            names="Situação",
            values="Quantidade",
            hole=0.3,
            color_discrete_sequence=px.colors.qualitative.Set1,  # cores fortes
        )
        fig_sit.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_sit, use_container_width=True)

    # Funcionários por escola
    with colg2:
        st.subheader("Por escola")
        esc_counts = df["Escola"].value_counts().reset_index()
        esc_counts.columns = ["Escola", "Quantidade"]
        fig_esc = px.pie(
            esc_counts,
            names="Escola",
            values="Quantidade",
            hole=0.3,
            color_discrete_sequence=px.colors.qualitative.Dark2,  # cores fortes
        )
        fig_esc.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_esc, use_container_width=True)

    # Funcionários por supervisor
    with colg3:
        st.subheader("Por supervisor")
        sup_counts = df["Supervisor"].value_counts().reset_index()
        sup_counts.columns = ["Supervisor", "Quantidade"]
        fig_sup = px.pie(
            sup_counts,
            names="Supervisor",
            values="Quantidade",
            hole=0.3,
            color_discrete_sequence=px.colors.qualitative.Bold,  # cores fortes
        )
        fig_sup.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_sup, use_container_width=True)

    # Exportar tudo que o admin vê
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Funcionarios")
    output.seek(0)

    st.download_button(
        label="📥 Baixar todos os dados em Excel (admin)",
        data=output,
        file_name="funcionarios_admin.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------ MAIN ------------------

def main():
    if not st.session_state.logged_in:
        show_auth_screen()
    else:
        if st.session_state.is_admin:
            tab1, tab2 = st.tabs(["Meus funcionários", "Dashboard Admin"])
            with tab1:
                show_employees_screen()
            with tab2:
                show_admin_dashboard()
        else:
            show_employees_screen()


if __name__ == "__main__":
    main()
