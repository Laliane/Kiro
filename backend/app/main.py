import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, sessions, admin

logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Consultant Advisor",
    description="API para análise de dados com LLM e busca por similaridade vetorial",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """
    Carrega automaticamente a base de conhecimento do CSV ao iniciar a aplicação.

    Verifica se o ChromaDB está vazio e, se estiver, carrega um CSV padrão
    especificado pela variável de ambiente DEFAULT_KB_CSV_PATH.

    Se o ChromaDB já tiver dados, pula o carregamento.
    """
    from app.database import get_records_collection
    from app.services.csv_preprocessor import CSVPreprocessor

    logger.info("Iniciando verificação da base de conhecimento...")

    # Verifica se o ChromaDB está vazio
    try:
        collection = get_records_collection()
        record_count = collection.count()

        if record_count > 0:
            logger.info(f"Base de conhecimento já carregada com {record_count} registros.")
            return

        logger.info("Base de conhecimento vazia. Tentando carregar CSV padrão...")

        # Tenta carregar CSV padrão
        default_csv_path = os.environ.get("DEFAULT_KB_CSV_PATH")

        if not default_csv_path:
            logger.warning(
                "Variável DEFAULT_KB_CSV_PATH não configurada. "
                "Base de conhecimento permanecerá vazia até upload manual."
            )
            return

        csv_path = Path(default_csv_path)

        if not csv_path.exists():
            logger.warning(
                f"Arquivo CSV padrão não encontrado: {default_csv_path}. "
                "Base de conhecimento permanecerá vazia até upload manual."
            )
            return

        # Carrega o CSV
        logger.info(f"Carregando CSV da base de conhecimento: {default_csv_path}")
        preprocessor = CSVPreprocessor()
        result = preprocessor.load(str(csv_path))

        logger.info(
            f"Base de conhecimento carregada com sucesso! "
            f"Processados: {result.processed_count}, "
            f"Ignorados: {result.skipped_count}, "
            f"Atualizados: {result.updated_count}"
        )

        if result.error_log:
            logger.warning(f"Erros durante o carregamento: {result.error_log[:5]}")

    except Exception as exc:
        logger.error(f"Erro ao verificar/carregar base de conhecimento: {exc}")
        # Não falha a inicialização, apenas loga o erro


app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
