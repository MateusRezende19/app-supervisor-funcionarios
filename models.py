from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from uuid import UUID


# Situações permitidas
StatusType = Literal["Trabalhando", "Abandono"]


class School(BaseModel):
    id: int
    name: str


class EmployeeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cpf: str = Field(..., min_length=11, max_length=11)
    school_id: int
    status: StatusType

    @validator("cpf")
    def cpf_must_be_11_digits(cls, v: str) -> str:
        """
        Garante que o CPF terá exatamente 11 dígitos numéricos.
        Aceita formatos com pontuação, mas armazena só números.
        """
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve conter exatamente 11 dígitos numéricos.")
        return digits


class EmployeeCreate(EmployeeBase):
    """
    Dados para cadastrar novo funcionário.
    """
    pass


class EmployeeUpdate(BaseModel):
    """
    Campos opcionais para atualização de funcionário.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    cpf: Optional[str] = Field(None, min_length=11, max_length=11)
    school_id: Optional[int] = None
    status: Optional[StatusType] = None

    @validator("cpf")
    def cpf_must_be_11_digits(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve conter exatamente 11 dígitos numéricos.")
        return digits


class Employee(EmployeeBase):
    """
    Representação completa de um funcionário vindo do Supabase.
    """
    id: UUID
    user_id: UUID
    created_at: str
    updated_at: str
