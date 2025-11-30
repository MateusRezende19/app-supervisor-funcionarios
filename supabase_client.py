import os
from typing import Any, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client

from models import (
    Employee,
    EmployeeCreate,
    EmployeeUpdate,
    School,
)

# Carrega variáveis do .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL ou SUPABASE_KEY não configurados no .env")

# Instância global do client Supabase (singleton)
_supabase: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Retorna uma instância singleton do client Supabase.
    """
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


# ---------- AUTENTICAÇÃO ----------

def _attach_session_to_postgrest(client: Client, session) -> None:
    """
    Configura o token JWT na camada PostgREST para que o RLS funcione.
    """
    if session and getattr(session, "access_token", None):
        client.postgrest.auth(session.access_token)


def sign_up(email: str, password: str) -> dict:
    """
    Cria um novo usuário no Supabase Auth.
    Retorna dict com user e session (se houver).
    """
    sb = get_supabase_client()
    response = sb.auth.sign_up({"email": email, "password": password})
    _attach_session_to_postgrest(sb, response.session)
    return {"user": response.user, "session": response.session}


def sign_in(email: str, password: str) -> dict:
    """
    Faz login com email/senha.
    Configura o token JWT no client para as queries respeitarem o RLS.
    """
    sb = get_supabase_client()
    response = sb.auth.sign_in_with_password({"email": email, "password": password})
    _attach_session_to_postgrest(sb, response.session)
    return {"user": response.user, "session": response.session}


# ... resto dos imports e código acima mantidos ...

# ---------- AUTENTICAÇÃO ----------

def sign_out() -> None:
    """
    Faz logout e reseta o client Supabase.
    Na próxima chamada, um novo client sem token será criado.
    """
    global _supabase
    if _supabase is None:
        return

    # Tenta encerrar a sessão atual (se houver)
    try:
        _supabase.auth.sign_out()
    except Exception:
        pass

    # Zera a instância; get_supabase_client() criará outra sem auth
    _supabase = None



def get_current_user_id() -> Optional[str]:
    """
    Retorna o ID do usuário logado baseado na sessão atual.
    """
    sb = get_supabase_client()
    response = sb.auth.get_user()
    user = getattr(response, "user", None)
    if user is not None:
        return user.id
    return None


# ---------- SCHOOLS (escolas) ----------

def list_schools() -> List[School]:
    """
    Retorna a lista de escolas cadastradas.
    Todos usuários autenticados podem ler.
    """
    sb = get_supabase_client()
    response = sb.table("schools").select("*").order("name", desc=False).execute()
    rows = response.data or []
    return [School(**row) for row in rows]


# ---------- EMPLOYEES (funcionários) ----------

def list_employees() -> List[Employee]:
    """
    Lista funcionários do supervisor logado.
    O RLS garante que só os funcionários do usuário atual sejam retornados.
    """
    sb = get_supabase_client()
    response = (
        sb.table("employees")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    rows = response.data or []
    return [Employee(**row) for row in rows]


def create_employee(data: EmployeeCreate) -> Employee:
    """
    Cadastra um novo funcionário para o supervisor logado.
    """
    sb = get_supabase_client()
    user_id = get_current_user_id()
    if not user_id:
        raise RuntimeError("Nenhum usuário logado para cadastrar funcionário.")

    payload = {
        "user_id": user_id,
        "name": data.name,
        "cpf": data.cpf,
        "school_id": data.school_id,
        "status": data.status,
    }

    response = sb.table("employees").insert(payload).execute()
    if not response.data:
        raise RuntimeError("Erro ao criar funcionário no Supabase.")

    return Employee(**response.data[0])


def update_employee(employee_id: str, data: EmployeeUpdate) -> Employee:
    """
    Atualiza um funcionário específico do supervisor logado.
    RLS garante que só atualiza se pertencer ao usuário.
    """
    sb = get_supabase_client()
    update_payload: dict[str, Any] = {}

    if data.name is not None:
        update_payload["name"] = data.name
    if data.cpf is not None:
        update_payload["cpf"] = data.cpf
    if data.school_id is not None:
        update_payload["school_id"] = data.school_id
    if data.status is not None:
        update_payload["status"] = data.status

    if not update_payload:
        raise ValueError("Nenhum campo para atualizar.")

    response = (
        sb.table("employees")
        .update(update_payload)
        .eq("id", employee_id)
        .execute()
    )

    if not response.data:
        raise RuntimeError("Funcionário não encontrado ou não pertence ao usuário logado.")

    return Employee(**response.data[0])


def delete_employee(employee_id: str) -> None:
    """
    Deleta um funcionário específico do supervisor logado.
    """
    sb = get_supabase_client()
    sb.table("employees").delete().eq("id", employee_id).execute()
