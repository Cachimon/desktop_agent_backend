from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_llm_instance: BaseChatModel | None = None


def get_llm() -> BaseChatModel:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    settings = get_settings()
    model_name = settings.llm.MODEL_NAME
    api_key = settings.llm.API_KEY or None
    api_base = settings.llm.API_BASE or None
    model_provider = settings.llm.MODEL_PROVIDER or None

    init_kwargs: dict = {
        "temperature": settings.llm.TEMPERATURE,
        "max_tokens": settings.llm.MAX_TOKENS,
    }
    if api_key:
        init_kwargs["api_key"] = api_key
    if api_base:
        init_kwargs["base_url"] = api_base
    if model_provider:
        init_kwargs["model_provider"] = model_provider

    llm = init_chat_model(model_name, **init_kwargs)
    _llm_instance = llm
    logger.info("llm_initialized", model=model_name)
    return _llm_instance
