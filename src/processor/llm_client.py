import re
import json as json_mod

from openai import AsyncOpenAI

from src.utils.logger import get_logger
from src.utils.key_store import load as load_keys

logger = get_logger(__name__)

MAX_RETRIES = 3


class LLMClient:
    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        keys = load_keys()
        self.api_key = api_key or keys.get("deepseek_api_key", "")
        self.base_url = base_url or keys.get("deepseek_base_url", "https://api.deepseek.com")
        self.model = model or "deepseek-chat"
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self._total_prompt_tokens + self._total_completion_tokens

    async def chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3, max_tokens: int = 4096) -> str:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                usage = resp.usage
                if usage:
                    self._total_prompt_tokens += usage.prompt_tokens or 0
                    self._total_completion_tokens += usage.completion_tokens or 0

                content = resp.choices[0].message.content
                if content:
                    return content
                logger.warning(f"LLM returned empty content (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"LLM call attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise

        return ""

    async def chat_json(self, system_prompt: str, user_prompt: str,
                        temperature: float = 0.3,
                        max_tokens: int = 4096) -> dict:
        raw = await self.chat(system_prompt, user_prompt, temperature, max_tokens)

        json_str = None
        m = re.search(r"```json\s*([\s\S]*?)\s*```", raw)
        if m:
            json_str = m.group(1)
        else:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                json_str = m.group(0)

        if json_str:
            try:
                return json_mod.loads(json_str)
            except json_mod.JSONDecodeError as e:
                logger.warning(f"JSON decode failed: {e}")

        logger.warning(f"Failed to extract JSON from LLM response. Raw: {raw[:500]}")
        return {}
