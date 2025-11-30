from supabase_client import sign_up, sign_in, list_tasks, create_task
from models import TaskCreate

# 1) Teste de signup (rode uma vez com um email novo)
# resp_signup = sign_up("seu_email_teste+1@exemplo.com", "senha123456")
# print("Signup:", resp_signup)

# 2) Login
resp_signin = sign_in("rezendemateus39@gmail.com", "Oper@@2024")
print("Login:", resp_signin["user"].email)

# 3) Listar tarefas (deve vir vazio na primeira vez)
tasks = list_tasks()
print("Tarefas iniciais:", tasks)

# 4) Criar uma tarefa
new_task = create_task(TaskCreate(title="Primeira tarefa", description="Teste"))
print("Nova tarefa criada:", new_task)

# 5) Listar novamente
tasks = list_tasks()
print("Tarefas após inserção:", tasks)
