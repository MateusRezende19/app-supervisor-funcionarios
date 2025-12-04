import streamlit as st
import pandas as pd
from io import BytesIO
import plotly.express as px
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from models import (
    EmployeeCreate,
    EmployeeUpdate,
    ObservationCreate,
)
from supabase_client import (
    sign_in,
    sign_up,
    sign_out,
    list_schools,
    list_employees,
    create_employee,
    update_employee,
    delete_employee,
    create_observation,
    list_observations,
    update_observation,  # para editar observações
)

# ====== CONFIGURAÇÃO DE ADMIN ======
ADMIN_EMAILS = {
    "monitoramento.conae@gmail.com",  # <- e-mails admin
}

# Lista de funções possíveis do colaborador
JOB_ROLES = [
    "Auxiliar de Limpeza",
    "Agente de Higienização",
    "Limpador de Vidros",
    "Lider",
    "Encarregado",
]

TZ_BR = ZoneInfo("America/Sao_Paulo")


def format_br_datetime(dt_str: str) -> str:
    """
    Converte string ISO (UTC) vinda do Supabase para data/hora em Brasília.
    Formato exibido: dd/mm/aaaa HH:MM
    """
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_br = dt.astimezone(TZ_BR)
        return dt_br.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt_str


# Wrapper para funcionar em versões novas/antigas do Streamlit
def rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


st.set_page_config(page_title="Artemis", layout="wide")

BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "assets" / "artemis_logo.png"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# view atual do supervisor: "employees" ou "observations"
if "current_view" not in st.session_state:
    st.session_state.current_view = "employees"


def do_logout():
    """Efetua logout e limpa o estado da sessão."""
    sign_out()
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.is_admin = False
    st.session_state.current_view = "employees"
    rerun()


def render_sidebar_header():
    """Logo + info de usuário na barra lateral + navegação."""
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), use_container_width=True)

    if st.session_state.logged_in:
        # Info de usuário
        if st.session_state.is_admin:
            st.sidebar.write(f"Logado como (ADMIN): **{st.session_state.user_email}**")
        else:
            st.sidebar.write(f"Logado como: **{st.session_state.user_email}**")

        if st.sidebar.button("Sair"):
            do_logout()

        # Navegação só para supervisor
        if not st.session_state.is_admin:
            st.sidebar.markdown("---")
            if st.session_state.current_view == "employees":
                if st.sidebar.button("📝 Observações"):
                    st.session_state.current_view = "observations"
                    rerun()
            else:
                if st.sidebar.button("👥 Funcionários"):
                    st.session_state.current_view = "employees"
                    rerun()


# ------------------ TELAS ------------------


def show_auth_screen():
    """Tela com abas de Login e Criar conta, logo e formulário centralizados."""

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_esq, col_centro, col_dir = st.columns([1, 2, 1])

    with col_centro:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=220)

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
                            st.session_state.current_view = "employees"
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
                            st.success(
                                "Conta criada com sucesso! Agora faça login na aba 'Login'."
                            )
                    except Exception as e:
                        st.error(f"Erro ao criar conta: {e}")


def show_employees_screen():
    """Tela principal de supervisão de funcionários (apenas dados do usuário)."""
    render_sidebar_header()

    # inicializa página da lista (paginação)
    if "emp_page" not in st.session_state:
        st.session_state.emp_page = 1

    # filtros persistentes
    if "filters" not in st.session_state:
        st.session_state.filters = {"name": "", "cpf": "", "school": "Todas"}

    st.title("Supervisão de Funcionários")

    # Mensagem de ação (ex: cadastro realizado)
    if "last_action_message" in st.session_state:
        msg = st.session_state.pop("last_action_message")
        if msg:
            st.success(msg)

    # Carregar escolas
    try:
        schools = list_schools()
    except Exception as e:
        st.error(f"Erro ao carregar escolas: {e}")
        return

    if not schools:
        st.warning(
            "Nenhuma escola cadastrada. Cadastre escolas direto no Supabase (tabela 'schools')."
        )
        return

    # id -> nome
    school_map = {s.id: s.name for s in schools}
    school_labels = {s.name: s.id for s in schools}

    # ---------- FORM NOVO FUNCIONÁRIO ----------
    st.subheader("Cadastrar novo funcionário")

    with st.form("new_employee_form", clear_on_submit=True):
        name = st.text_input("Nome do funcionário", max_chars=200)
        cpf = st.text_input("CPF (somente números ou com pontuação)", max_chars=14)

        # Escola
        school_options = ["Selecione a escola"] + list(school_labels.keys())
        selected_school_label = st.selectbox("Escola", school_options, index=0)

        # Função
        role_options = ["Selecione a função"] + JOB_ROLES
        role = st.selectbox("Função", role_options, index=0)

        # Situação
        status_options = ["Selecione a situação", "Trabalhando", "Abandono"]
        status = st.selectbox("Situação", status_options, index=0)

        submitted = st.form_submit_button("Cadastrar")

    if submitted:
        name_clean = name.strip()
        cpf_clean = cpf.strip()

        if (
            not name_clean
            or not cpf_clean
            or selected_school_label == "Selecione a escola"
            or role == "Selecione a função"
            or status == "Selecione a situação"
        ):
            st.warning("Nome, CPF, escola, função e situação são obrigatórios.")
        else:
            school_id = school_labels[selected_school_label]
            try:
                create_employee(
                    EmployeeCreate(
                        name=name_clean,
                        cpf=cpf_clean,
                        school_id=school_id,
                        status=status,
                        role=role,
                    )
                )
                st.session_state.emp_page = 1
                st.session_state.last_action_message = (
                    "Funcionário cadastrado com sucesso."
                )
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

    # Se for admin logado (edge case), ainda mostra só dele
    if st.session_state.is_admin:
        user_email = st.session_state.user_email
        employees = [e for e in employees if e.user_email == user_email]

    if not employees:
        st.info("Nenhum funcionário cadastrado por você.")
        return

    # ----- FILTROS COM BOTÃO "APLICAR" -----
    with st.expander("Filtros", expanded=False):
        with st.form("filter_form"):
            current_filters = st.session_state.filters
            filter_name_input = st.text_input(
                "Filtrar por nome", value=current_filters["name"]
            )
            filter_cpf_input = st.text_input(
                "Filtrar por CPF", value=current_filters["cpf"]
            )

            school_filter_options = ["Todas"] + list(school_labels.keys())
            current_school = current_filters["school"]
            try:
                idx_school = school_filter_options.index(current_school)
            except ValueError:
                idx_school = 0

            school_filter_label_input = st.selectbox(
                "Filtrar por escola", school_filter_options, index=idx_school
            )

            apply_filters = st.form_submit_button("Aplicar filtros")

        if apply_filters:
            st.session_state.filters = {
                "name": filter_name_input.strip(),
                "cpf": filter_cpf_input.strip(),
                "school": school_filter_label_input,
            }
            st.session_state.emp_page = 1
            rerun()

    # usa os filtros aplicados
    filter_name = st.session_state.filters["name"]
    filter_cpf = st.session_state.filters["cpf"]
    school_filter_label = st.session_state.filters["school"]

    employees_filtered = employees

    if filter_name:
        name_lower = filter_name.strip().lower()
        employees_filtered = [
            e for e in employees_filtered if name_lower in e.name.lower()
        ]

    if filter_cpf:
        cpf_digits_filter = "".join(ch for ch in filter_cpf if ch.isdigit())
        employees_filtered = [
            e
            for e in employees_filtered
            if cpf_digits_filter in "".join(ch for ch in e.cpf if ch.isdigit())
        ]

    if school_filter_label != "Todas":
        school_id_filter = school_labels[school_filter_label]
        employees_filtered = [
            e for e in employees_filtered if e.school_id == school_id_filter
        ]

    if not employees_filtered:
        st.info("Nenhum funcionário encontrado com os filtros aplicados.")
        return

    # ===== PAGINAÇÃO =====
    page_size = 10
    total_registros = len(employees_filtered)
    total_paginas = (total_registros - 1) // page_size + 1

    if st.session_state.emp_page > total_paginas:
        st.session_state.emp_page = total_paginas
    if st.session_state.emp_page < 1:
        st.session_state.emp_page = 1

    page = st.session_state.emp_page
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    employees_page = employees_filtered[start_idx:end_idx]

    # Métricas gerais
    total = len(employees_filtered)
    trabalhando = sum(1 for e in employees_filtered if e.status == "Trabalhando")
    abandono = sum(1 for e in employees_filtered if e.status == "Abandono")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total (com filtros)", total)
    col_b.metric("Trabalhando", trabalhando)
    col_c.metric("Abandono", abandono)

    # Exportar todos os filtrados
    df = pd.DataFrame(
        [
            {
                "Nome": e.name,
                "CPF": e.cpf,
                "Escola": school_map.get(e.school_id, f"ID {e.school_id}"),
                "Função": e.role,
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

    # Lista detalhada APENAS da página atual
    for emp in employees_page:
        with st.container():
            cols = st.columns([0.35, 0.2, 0.2, 0.1, 0.15])

            with cols[0]:
                st.markdown(f"**{emp.name}**")
                st.caption(f"CPF: {emp.cpf}")
                st.caption(
                    f"Escola: {school_map.get(emp.school_id, f'ID {emp.school_id}')}"
                )
                st.caption(f"Função: {emp.role}")
                st.caption(
                    f"Cadastrado em: {format_br_datetime(emp.created_at)}"
                )
                st.caption(
                    f"Atualizado em: {format_br_datetime(emp.updated_at)}"
                )

            with cols[1]:
                status_badge = (
                    "🟢 Trabalhando"
                    if emp.status == "Trabalhando"
                    else "🔴 Abandono"
                )
                st.markdown(f"**Situação:** {status_badge}")

            with cols[2]:
                toggle_label = (
                    "Marcar Abandono"
                    if emp.status == "Trabalhando"
                    else "Marcar Trabalhando"
                )
                if st.button(toggle_label, key=f"toggle_{emp.id}"):
                    new_status = (
                        "Abandono"
                        if emp.status == "Trabalhando"
                        else "Trabalhando"
                    )
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

            # Formulário de edição
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
                    new_role = st.selectbox(
                        "Função",
                        JOB_ROLES,
                        index=JOB_ROLES.index(emp.role)
                        if emp.role in JOB_ROLES
                        else 0,
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
                                role=new_role,
                            ),
                        )
                        st.session_state[f"editing_{emp.id}"] = False
                        rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar edição: {e}")

                if cancel_clicked:
                    st.session_state[f"editing_{emp.id}"] = False
                    rerun()

    # Controles de paginação
    st.markdown("---")
    col_prev, col_info, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button("◀ Página anterior", disabled=(page <= 1)):
            st.session_state.emp_page = page - 1
            rerun()

    with col_info:
        st.markdown(
            f"<p style='text-align:center;'>Página {page} de {total_paginas}</p>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button("Próxima página ▶", disabled=(page >= total_paginas)):
            st.session_state.emp_page = page + 1
            rerun()


def show_observations_screen():
    """Tela de observações / reclamações do supervisor."""
    render_sidebar_header()
    st.title("Observações / Reclamações")

    # Carregar escolas
    try:
        schools = list_schools()
    except Exception as e:
        st.error(f"Erro ao carregar escolas: {e}")
        return

    if not schools:
        st.warning(
            "Nenhuma escola cadastrada. Cadastre escolas direto no Supabase (tabela 'schools')."
        )
        return

    school_map = {s.id: s.name for s in schools}
    school_labels = {s.name: s.id for s in schools}

    # Carregar funcionários do supervisor
    try:
        employees = list_employees()
    except Exception as e:
        st.error(f"Erro ao carregar funcionários: {e}")
        return

    employees_by_id = {str(e.id): e for e in employees}
    emp_label_map = {
        f"{e.name} - {school_map.get(e.school_id, f'ID {e.school_id}')}"
        : str(e.id)
        for e in employees
    }

    # ---------- NOVA OBSERVAÇÃO ----------
    st.subheader("Registrar nova observação")

    with st.form("obs_form", clear_on_submit=True):
        tipo = st.radio("Tipo de observação", ["Colaborador", "Escola"])

        selected_employee_id = None
        selected_school_id = None

        if tipo == "Colaborador":
            emp_options = ["Selecione o colaborador"] + list(emp_label_map.keys())
            emp_label = st.selectbox("Colaborador", emp_options, index=0)

            school_options = ["Selecione a escola"] + list(school_labels.keys())
            default_index = 0
            if emp_label != "Selecione o colaborador":
                emp_id = emp_label_map[emp_label]
                selected_employee_id = emp_id
                emp_obj = employees_by_id[emp_id]
                if emp_obj.school_id in school_map:
                    school_name_default = school_map[emp_obj.school_id]
                    default_index = 1 + list(school_labels.keys()).index(
                        school_name_default
                    )

            selected_school_label = st.selectbox(
                "Escola", school_options, index=default_index
            )
            if selected_school_label != "Selecione a escola":
                selected_school_id = school_labels[selected_school_label]

        else:  # Escola
            school_options = ["Selecione a escola"] + list(school_labels.keys())
            selected_school_label = st.selectbox("Escola", school_options, index=0)
            if selected_school_label != "Selecione a escola":
                selected_school_id = school_labels[selected_school_label]

        texto = st.text_area("Descrição da observação")
        submitted = st.form_submit_button("Registrar observação")

    if submitted:
        texto_clean = texto.strip()

        if tipo == "Colaborador":
            if not selected_employee_id or not selected_school_id or not texto_clean:
                st.warning(
                    "Selecione o colaborador, a escola e preencha a observação."
                )
            else:
                try:
                    create_observation(
                        ObservationCreate(
                            type="COLABORADOR",
                            employee_id=selected_employee_id,
                            school_id=selected_school_id,
                            text=texto_clean,
                        )
                    )
                    st.success("Observação registrada com sucesso.")
                    rerun()
                except Exception as e:
                    st.error(f"Erro ao registrar observação: {e}")
        else:
            if not selected_school_id or not texto_clean:
                st.warning("Selecione a escola e preencha a observação.")
            else:
                try:
                    create_observation(
                        ObservationCreate(
                            type="ESCOLA",
                            employee_id=None,
                            school_id=selected_school_id,
                            text=texto_clean,
                        )
                    )
                    st.success("Observação registrada com sucesso.")
                    rerun()
                except Exception as e:
                    st.error(f"Erro ao registrar observação: {e}")

    st.markdown("---")

    # ---------- LISTA DE OBSERVAÇÕES ----------
    st.subheader("Minhas observações cadastradas")

    try:
        observations = list_observations()
    except Exception as e:
        st.error(f"Erro ao carregar observações: {e}")
        return

    if not observations:
        st.info("Nenhuma observação cadastrada ainda.")
        return

    escolas_usadas = sorted(
        {
            school_map.get(o.school_id, f"ID {o.school_id}")
            for o in observations
            if o.school_id
        }
    )
    colaboradores_usados = sorted(
        {
            employees_by_id.get(str(o.employee_id)).name
            for o in observations
            if o.employee_id and str(o.employee_id) in employees_by_id
        }
    )

    with st.expander("Filtros", expanded=False):
        tipo_filter = st.selectbox("Filtrar por tipo", ["Todos", "Colaborador", "Escola"])
        escola_filter = st.selectbox(
            "Filtrar por escola", ["Todas"] + escolas_usadas
        )
        colaborador_filter = st.selectbox(
            "Filtrar por colaborador", ["Todos"] + colaboradores_usados
        )

    obs_filtered = observations

    if tipo_filter == "Colaborador":
        obs_filtered = [o for o in obs_filtered if o.type == "COLABORADOR"]
    elif tipo_filter == "Escola":
        obs_filtered = [o for o in obs_filtered if o.type == "ESCOLA"]

    if escola_filter != "Todas":
        obs_filtered = [
            o
            for o in obs_filtered
            if school_map.get(o.school_id, f"ID {o.school_id}") == escola_filter
        ]

    if colaborador_filter != "Todos":
        obs_filtered = [
            o
            for o in obs_filtered
            if (
                o.employee_id
                and str(o.employee_id) in employees_by_id
                and employees_by_id[str(o.employee_id)].name == colaborador_filter
            )
        ]

    if not obs_filtered:
        st.info("Nenhuma observação encontrada com os filtros selecionados.")
        return

    # === LISTAGEM DETALHADA COM EDIÇÃO ===
    for o in obs_filtered:
        emp_name = "-"
        if o.employee_id and str(o.employee_id) in employees_by_id:
            emp_name = employees_by_id[str(o.employee_id)].name.upper()

        escola_name = (
            school_map.get(o.school_id, f"ID {o.school_id}") if o.school_id else "-"
        )
        tipo_legivel = "Colaborador" if o.type == "COLABORADOR" else "Escola"
        data_label = format_br_datetime(o.created_at)

        with st.container():
            st.markdown("---")
            c1, c2, c3, c4, c5 = st.columns([0.18, 0.27, 0.15, 0.20, 0.10])

            with c1:
                st.markdown("**Colaborador**")
                st.write(emp_name)

            with c2:
                st.markdown("**Escola**")
                st.write(escola_name)

            with c3:
                st.markdown("**Tipo**")
                st.write(tipo_legivel)

            with c4:
                st.markdown("**Data**")
                st.write(data_label)

            with c5:
                if st.button("Editar", key=f"edit_obs_{o.id}"):
                    st.session_state[f"editing_obs_{o.id}"] = True

            if st.session_state.get(f"editing_obs_{o.id}", False):
                st.markdown("**Observação (editar)**")
                with st.form(f"edit_obs_form_{o.id}"):
                    new_text = st.text_area("", value=o.text, height=120)
                    col_save, col_cancel = st.columns(2)
                    save_clicked = col_save.form_submit_button("Salvar")
                    cancel_clicked = col_cancel.form_submit_button("Cancelar")

                if save_clicked:
                    try:
                        update_observation(str(o.id), new_text.strip())
                        st.session_state[f"editing_obs_{o.id}"] = False
                        st.success("Observação atualizada com sucesso.")
                        rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar observação: {e}")

                if cancel_clicked:
                    st.session_state[f"editing_obs_{o.id}"] = False
                    rerun()
            else:
                st.markdown("**Observação**")
                st.write(o.text)


def show_admin_dashboard():
    """Dashboard para usuário admin: visão consolidada de todos os funcionários."""
    render_sidebar_header()
    st.title("Dashboard Administrativo - Visão Geral")

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

    # DataFrame base
    df = pd.DataFrame(
        [
            {
                "Nome": e.name,
                "CPF": e.cpf,
                "Escola": school_map.get(e.school_id, f"ID {e.school_id}"),
                "Função": e.role,
                "Situação": e.status,
                "Supervisor": e.user_email,
                "Cadastrado em (Brasília)": format_br_datetime(e.created_at),
                "Atualizado em (Brasília)": format_br_datetime(e.updated_at),
            }
            for e in employees
        ]
    )

    # ===== MÉTRICAS GERAIS POR SITUAÇÃO =====
    total = len(df)
    total_trabalhando = (df["Situação"] == "Trabalhando").sum()
    total_abandono = (df["Situação"] == "Abandono").sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de funcionários", total)
    col2.metric("Trabalhando", total_trabalhando)
    col3.metric("Abandono", total_abandono)

    st.markdown("---")

    # ===== GRÁFICO DE BARRAS: FUNCIONÁRIOS POR SUPERVISOR =====
    st.subheader("Funcionários cadastrados por supervisor")

    df_sup = (
        df.groupby("Supervisor")["Nome"]
        .count()
        .reset_index(name="Quantidade")
        .sort_values("Quantidade", ascending=False)
    )

    fig_sup_bar = px.bar(
        df_sup,
        x="Supervisor",
        y="Quantidade",
        text="Quantidade",
        color="Supervisor",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_sup_bar.update_traces(textposition="outside")
    fig_sup_bar.update_layout(
        xaxis_title="Supervisor",
        yaxis_title="Quantidade de funcionários",
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=80),
    )

    st.plotly_chart(fig_sup_bar, use_container_width=True)

    st.markdown("---")

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

    st.markdown("### Funcionários cadastrados")

    df_table = pd.DataFrame(
        {
            "Nome": df["Nome"].str.upper(),
            "Escola": df["Escola"],
            "Função": df["Função"],
            "Situação": df["Situação"],
            "Data de cadastro": df["Cadastrado em (Brasília)"],
            "Data da última atualização": df["Atualizado em (Brasília)"],
        }
    )

    st.dataframe(df_table, use_container_width=True)


# ------------------ MAIN ------------------


def main():
    if not st.session_state.logged_in:
        show_auth_screen()
    else:
        if st.session_state.is_admin:
            show_admin_dashboard()
        else:
            if st.session_state.current_view == "observations":
                show_observations_screen()
            else:
                show_employees_screen()


if __name__ == "__main__":
    main()
