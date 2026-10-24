"""
Environment compatibility patch script for LegalDocAI.

Resolves:
1. docstring_parser 0.15 ast.NameConstant / ast.Num / ast.Str removal in Python 3.12+ (Python 3.14).
2. ragas 0.4.3 langchain_community.chat_models.vertexai removal in langchain_community 0.4+.
"""

import ast
import site
import sys
from pathlib import Path


def patch_docstring_parser():
    try:
        import docstring_parser.attrdoc as target_mod
    except Exception as exc:
        print(f"[SKIP] docstring_parser cannot be imported: {exc}")
        return

    file_path = Path(target_mod.__file__)
    content = file_path.read_text(encoding="utf-8")
    if "ast_constant_attr: dict = {ast.Constant: \"value\"}" in content:
        print(f"[OK] docstring_parser already patched: {file_path}")
        return

    old_target = """ast_constant_attr = {
    ast.Constant: "value",
    # python <= 3.7:
    ast.NameConstant: "value",
    ast.Num: "n",
    ast.Str: "s",
}"""

    new_target = """ast_constant_attr: dict = {ast.Constant: "value"}
for _legacy_type, _attr in (
    ("NameConstant", "value"),
    ("Num", "n"),
    ("Str", "s"),
):
    _node_cls = getattr(ast, _legacy_type, None)
    if _node_cls is not None:
        ast_constant_attr[_node_cls] = _attr"""

    if old_target in content:
        content = content.replace(old_target, new_target)
        file_path.write_text(content, encoding="utf-8")
        print(f"[PATCHED] docstring_parser at {file_path}")
    else:
        print("[NOTE] docstring_parser pattern not found (already compatible or different version).")


def patch_ragas():
    # Find ragas/llms/base.py in site-packages
    candidate_paths = []
    for sp in site.getsitepackages():
        p = Path(sp) / "ragas" / "llms" / "base.py"
        if p.exists():
            candidate_paths.append(p)

    for file_path in candidate_paths:
        content = file_path.read_text(encoding="utf-8")
        target_import = "from langchain_community.chat_models.vertexai import ChatVertexAI\nfrom langchain_community.llms import VertexAI"
        replacement_import = """try:
    from langchain_community.chat_models.vertexai import ChatVertexAI
    from langchain_community.llms import VertexAI
except ImportError:
    try:
        from langchain_google_vertexai import ChatVertexAI, VertexAI
    except ImportError:
        ChatVertexAI = None
        VertexAI = None"""

        if target_import in content:
            content = content.replace(target_import, replacement_import)
            content = content.replace(
                "MULTIPLE_COMPLETION_SUPPORTED = [\n    OpenAI,\n    ChatOpenAI,\n    AzureOpenAI,\n    AzureChatOpenAI,\n    ChatVertexAI,\n    VertexAI,\n]",
                "MULTIPLE_COMPLETION_SUPPORTED = [\n    cls for cls in [\n        OpenAI,\n        ChatOpenAI,\n        AzureOpenAI,\n        AzureChatOpenAI,\n        ChatVertexAI,\n        VertexAI,\n    ] if cls is not None\n]"
            )
            file_path.write_text(content, encoding="utf-8")
            print(f"[PATCHED] ragas at {file_path}")
        else:
            print(f"[OK] ragas already patched: {file_path}")


if __name__ == "__main__":
    patch_docstring_parser()
    patch_ragas()
    print("Environment compatibility check complete.")
