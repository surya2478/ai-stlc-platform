import os, json
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models.agent import AgentRun

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
        run = session.get(AgentRun, 69)
        if run:
            print(f"Run ID: {run.id}")
            print(f"Agent Name: {run.agent_name}")
            print(f"Status: {run.status}")
            print(f"Input Data: {json.dumps(run.input_data, indent=2) if run.input_data else None}")
            print(f"Output Data: {json.dumps(run.output_data, indent=2) if run.output_data else None}")
            print(f"Metadata: {json.dumps(run.metadata_, indent=2) if run.metadata_ else None}")
            print(f"Agent Result: {run.agent_result}")
        else:
            print("Run 69 not found!")
            
    finally:
        session.close()

if __name__ == "__main__":
    query_db()
