import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models.agent import AgentLog

def load_dotenv_manually():
    env_vars = {}
    env_path = "c:/Test_AI_Agents/Test_AI_Agents/stlc-platform/.env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def query_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        env_vars = load_dotenv_manually()
        database_url = env_vars.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stlc_agents")
        database_url = database_url.replace("@db:", "@localhost:")
    
    print(f"Connecting to database: {database_url.split('@')[-1]}")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    session = Session()
    try:
        logs = session.execute(
            select(AgentLog)
            .where(AgentLog.agent_run_id == 69)
            .order_by(AgentLog.id.ascii() if hasattr(AgentLog.id, 'ascii') else AgentLog.id.asc())
        ).scalars().all()
        
        print(f"Total log entries for run 69: {len(logs)}")
        for l in logs:
            print(f"[{l.level.upper()}] Step: {l.step} - Message: {l.message}")
            if l.data:
                print(f"  Data: {l.data}")
            print("-" * 30)
            
    finally:
        session.close()

if __name__ == "__main__":
    query_db()
