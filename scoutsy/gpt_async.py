import asyncio

import aiosqlite
import openai
import tiktoken
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
from tqdm.asyncio import tqdm


def parse_reponse(response):
    if "candidate_1" in response or "candidate_2" in response:
        return response
    else:
        raise ValueError("__Invalid response")


def count_token(prompt, token_encoding_name="o200k_base"):
    token_per_message = 3
    token_per_name = 1  # not sure about this
    enc = tiktoken.get_encoding(token_encoding_name)
    return len(enc.encode(prompt)) + token_per_message + token_per_name


@retry(
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(3),
    retry=retry_if_not_exception_type(openai.BadRequestError),
    before_sleep=before_sleep_log(logger, 0),
)
async def get_response(client: openai.OpenAI, messages, model):
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
    )
    usage = response.usage
    return response.choices[0].message.content, usage


def compute_winner(llm_response, accepted_id, rejected_id, order):
    if llm_response not in {"candidate_1", "candidate_2"}:
        raise ValueError("_invalid response")

    is_accepted_first = order == "accepted_rejected"

    if llm_response == "candidate_1":
        return accepted_id if is_accepted_first else rejected_id
    else:  # llm_response == "candidate_2"
        return rejected_id if is_accepted_first else accepted_id


def clean_string_sql(string):
    return string.replace("'", "''").replace('"', '""')


async def process_one_prompt(client, prompt, system_prompt, model, db_cursor, pbar):
    insert_query = None
    status = "invalid"
    response = ""
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt["text"]},
        ]
        response, usage = await get_response(client, messages, model)
        llm_response = parse_reponse(response)
        winner_resource_id = compute_winner(
            llm_response,
            prompt["accepted_resource_id"],
            prompt["rejected_resource_id"],
            prompt["order"],
        )
        input_token_usage = usage.prompt_tokens
        output_token_usage = usage.completion_tokens
        status = "valid"
        error = "None"
        insert_query = f"""INSERT INTO PairsPromptResult (pairs_prompt_id, model_name, winner_resource_id, llm_response, input_token_usage,output_token_usage,status,error) VALUES ({prompt["id"]}, "{model}", {winner_resource_id}, "{response}", {input_token_usage},{output_token_usage},"{status}","{error}")"""

    except asyncio.TimeoutError:
        logger.debug("TimeoutError")
        insert_query = f"""INSERT INTO PairsPromptResult (pairs_prompt_id, model_name, winner_resource_id, error, status,llm_response) VALUES ({prompt["id"]}, "{model}", 937,"TimeoutError", "{status}","{clean_string_sql(response)}")"""
        logger.error(f"response: {response}")
    except ValueError as exc:
        logger.debug("ValueError")
        insert_query = f"""INSERT INTO PairsPromptResult (pairs_prompt_id, model_name,winner_resource_id, error, status,llm_response) VALUES ({prompt["id"]}, "{model}",937, "{clean_string_sql(str(exc))}", "{status}","{clean_string_sql(response)}")"""
        logger.error(f"response: {response}")

    except Exception as exc:
        logger.debug("Unknown Error")
        insert_query = f"""INSERT INTO PairsPromptResult (pairs_prompt_id, model_name, winner_resource_id, error, status,llm_response) VALUES ({prompt["id"]}, "{model}", 937, "{str(exc).replace("'", "''").replace('"', '""')}", "{status}", "{clean_string_sql(response)}")"""
        logger.error(f"Error: {str(exc)}")

    finally:
        await db_cursor.execute(insert_query)
        pbar.update(1)


async def process_one_summary_prompt(
    client, prompt, system_prompt, model, cursor, pbar
):
    status = "invalid"
    response = ""
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt["text"]},
        ]
        response, usage = await get_response(client, messages, model)
        status = "valid"
        insert_query = r"""INSERT INTO ResourceSummary (resource_id, model_name, summary_prompt, summary, input_tokens, output_tokens,status) VALUES (?,?,?,?,?,?,?)"""
        await cursor.execute(
            insert_query,
            (
                prompt["resource_id"],
                model,
                prompt["text"],
                clean_string_sql(response),
                usage.prompt_tokens,
                usage.completion_tokens,
                status,
            ),
        )
    except Exception as exc:
        insert_query = r"""INSERT INTO ResourceSummary (resource_id, model_name, summary_prompt, summary, input_tokens, output_tokens,status) VALUES (?,?,?,?,?,?,?)"""
        await cursor.execute(
            insert_query,
            (
                prompt["resource_id"],
                model,
                prompt["text"],
                clean_string_sql(response),
                0,
                0,
                status,
            ),
        )
        logger.error(f"Error: {str(exc)}")

    pbar.update(1)


async def process_many_summary_promtps(client, prompts, system_prompt, model, src_db):
    conn = await aiosqlite.connect(src_db, autocommit=True)
    db_cursor = await conn.cursor()
    await db_cursor.execute("PRAGMA foreign_keys = ON")
    await db_cursor.execute("PRAGMA journal_mode = WAL")
    pbar = tqdm(total=len(prompts), desc="Processing prompts", colour="cyan")
    for indx, prompt in prompts.iterrows():
        await process_one_summary_prompt(
            client, prompt, system_prompt, model, db_cursor, pbar
        )
    await db_cursor.close()
    await conn.close()
    pbar.close()


async def process_many_prompt(client, prompts, system_prompt, model, src_db):
    conn = await aiosqlite.connect(src_db, autocommit=True)
    db_cursor = await conn.cursor()
    await db_cursor.execute("PRAGMA foreign_keys = ON")
    await db_cursor.execute("PRAGMA journal_mode = WAL")
    total_token = 0
    # lock = asyncio.Lock()
    # sem = asyncio.Semaphore(30)
    pbar = tqdm(total=len(prompts), desc="Processing prompts", colour="yellow")
    # async with sem:
    for indx, prompt in prompts.iterrows():
        await process_one_prompt(client, prompt, system_prompt, model, db_cursor, pbar)
    await db_cursor.close()
    await conn.close()
    pbar.close()
