import streamlit as st
import pandas as pd
from io import BytesIO

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

# Wrapper para funcionar em versões novas/antigas do Streamlit
def rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


st.set_page_config(page_title="Supervisão de Funcionários", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None


def do_logout():
    """Efetua logout e limpa o estado da sessão."""
    sign_out()
    st.session_state.logged_in = False
    st.session_state.user_email = None
    rerun()


# ------------------ TELAS ------------------


def show_auth_screen():
    """Tela com abas de Login e Criar conta."""
    st.title("Supervisão de Funcionários - Autenticação")

    tab_login, tab_signup = st.tabs(["Login", "Criar conta"])

    # ----- LOGIN -----
    with tab_login:
        st.subheader("Entrar")

        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")

        if submitted:
            if not email or not password:
                st.error("Preencha e-mail e senha.")
            else:
                try:
                    resp = sign_in(email, password)
                    user = resp["user"]
                    if user is None:
                        st.error("Credenciais inválidas.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user.email
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
            if not email_new or not password_new or not password_confirm:
                st.error("Preencha todos os campos.")
            elif password_new != password_confirm:
                st.error("As senhas não conferem.")
            elif len(password_new) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            else:
                try:
                    resp = sign_up(email_new, password_new)
                    user = resp["user"]
                    if user is None:
                        st.warning(
                            "Conta criada, mas pode ser necessário confirmar o e-mail "
                            "conforme config do Supabase."
                        )
                    else:
                        st.success("Conta criada com sucesso! Agora faça login na aba 'Login'.")
                except Exception as e:
                    st.error(f"Erro ao criar conta: {e}")


def show_employees_screen():
    """Tela principal de supervisão de funcionários."""
    st.sidebar.write(f"Logado como: **{st.session_state.user_email}**")
    if st.sidebar.button("Sair"):
        do_logout()

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

    school_map = {s.id: s.name for s in schools}
    school_labels = {f"{s.name} (ID {s.id})": s.id for s in schools}

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

    # ---------- LISTA DE FUNCIONÁRIOS (COM FILTROS E EXPORT) ----------
    st.subheader("Funcionários cadastrados")

    try:
        employees = list_employees()
    except Exception as e:
        st.error(f"Erro ao carregar funcionários: {e}")
        return

    if not employees:
        st.info("Nenhum funcionário cadastrado ainda.")
        return

    # ----- FILTROS -----
    with st.expander("Filtros", expanded=False):
        filter_name = st.text_input("Filtrar por nome")
        filter_cpf = st.text_input("Filtrar por CPF")
        school_filter_options = ["Todas"] + list(school_labels.keys())
        school_filter_label = st.selectbox("Filtrar por escola", school_filter_options, index=0)

    employees_filtered = employees

    # filtro por nome (case-insensitive, contém)
    if filter_name:
        name_lower = filter_name.strip().lower()
        employees_filtered = [
            e for e in employees_filtered if name_lower in e.name.lower()
        ]

    # filtro por CPF (compara somente dígitos)
    if filter_cpf:
        cpf_digits_filter = "".join(ch for ch in filter_cpf if ch.isdigit())
        employees_filtered = [
            e
            for e in employees_filtered
            if cpf_digits_filter in "".join(ch for ch in e.cpf if ch.isdigit())
        ]

    # filtro por escola
    if school_filter_label != "Todas":
        school_id_filter = school_labels[school_filter_label]
        employees_filtered = [
            e for e in employees_filtered if e.school_id == school_id_filter
        ]

    if not employees_filtered:
        st.info("Nenhum funcionário encontrado com os filtros aplicados.")
        return

    # ----- RESUMO / MÉTRICAS DOS FILTRADOS -----
    total = len(employees_filtered)
    trabalhando = sum(1 for e in employees_filtered if e.status == "Trabalhando")
    abandono = sum(1 for e in employees_filtered if e.status == "Abandono")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total (com filtros)", total)
    col_b.metric("Trabalhando", trabalhando)
    col_c.metric("Abandono", abandono)

    # ----- EXPORTAR PARA EXCEL (DADOS FILTRADOS) -----
    df = pd.DataFrame(
        [
            {
                "Nome": e.name,
                "CPF": e.cpf,
                "Escola": school_map.get(e.school_id, f"ID {e.school_id}"),
                "Situação": e.status,
                "Criado em": e.created_at,
                "Atualizado em": e.updated_at,
            }
            for e in employees_filtered
        ]
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Funcionarios")
    output.seek(0)

    st.download_button(
        label="📥 Baixar dados em Excel (filtros aplicados)",
        data=output,
        file_name="funcionarios_supervisao.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("---")

    # ----- LISTAGEM DETALHADA -----
    for emp in employees_filtered:
        with st.container():
            cols = st.columns([0.35, 0.2, 0.2, 0.1, 0.15])

            with cols[0]:
                st.markdown(f"**{emp.name}**")
                st.caption(f"CPF: {emp.cpf}")
                st.caption(f"Escola: {school_map.get(emp.school_id, f'ID {emp.school_id}')}")

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

            # Form de edição
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


# ------------------ MAIN ------------------

def main():
    if not st.session_state.logged_in:
        show_auth_screen()
    else:
        show_employees_screen()


if __name__ == "__main__":
    main()
