from sqlalchemy import select, func
from sqlalchemy.orm import Session
from modelforge_common.prompt_template import extract_params, validate_template
from app.models.prompt import Prompt, PromptVersion


def _params_of(system_prompt: str, user_prompt: str) -> list[str]:
    out: list[str] = []
    for name in extract_params(system_prompt) + extract_params(user_prompt):
        if name not in out:
            out.append(name)
    return out


def validate(system_prompt: str, user_prompt: str) -> dict:
    errors = validate_template(system_prompt) + validate_template(user_prompt)
    return {"params": _params_of(system_prompt, user_prompt), "errors": errors}


def create_prompt(db: Session, *, name: str, system_prompt: str, user_prompt: str,
                  note: str, created_by: int | None) -> Prompt:
    errs = validate_template(system_prompt) + validate_template(user_prompt)
    if errs:
        raise ValueError("; ".join(errs))
    p = Prompt(name=name, created_by=created_by)
    p.versions.append(PromptVersion(
        version_no=1, system_prompt=system_prompt, user_prompt=user_prompt,
        params=_params_of(system_prompt, user_prompt), note=note, created_by=created_by))
    db.add(p); db.commit(); db.refresh(p)
    return p


def add_version(db: Session, prompt_id: int, *, system_prompt: str, user_prompt: str,
                note: str, created_by: int | None) -> PromptVersion | None:
    p = db.get(Prompt, prompt_id)
    if not p:
        return None
    errs = validate_template(system_prompt) + validate_template(user_prompt)
    if errs:
        raise ValueError("; ".join(errs))
    next_no = (db.execute(
        select(func.coalesce(func.max(PromptVersion.version_no), 0))
        .where(PromptVersion.prompt_id == prompt_id)).scalar()) + 1
    v = PromptVersion(prompt_id=prompt_id, version_no=next_no, system_prompt=system_prompt,
                      user_prompt=user_prompt, params=_params_of(system_prompt, user_prompt),
                      note=note, created_by=created_by)
    db.add(v); db.commit(); db.refresh(v)
    return v
