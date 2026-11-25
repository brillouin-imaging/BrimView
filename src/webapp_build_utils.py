import ast
import re


def replace_library_with_url(js_code, lib_name, custom_url):
    pattern = re.compile(r"(\bawait\s+micropip\.install\s*\()(\[.*?\])(\))", re.DOTALL)
    replacement = ast.parse(custom_url, mode="eval").body
    matches = 0

    def replace_install(match):
        nonlocal matches
        requirements = ast.parse(match.group(2), mode="eval").body
        for index, requirement in enumerate(requirements.elts):
            if not isinstance(requirement, ast.Constant) or not isinstance(requirement.value, str):
                continue
            name = re.split(r"[=<>!~\[ ;]", requirement.value, maxsplit=1)[0]
            if name == lib_name:
                requirements.elts[index] = replacement
                matches += 1
                return f"{match.group(1)}{ast.unparse(requirements)}{match.group(3)}"
        raise ValueError(f"Library '{lib_name}' not found in micropip install.")

    updated = pattern.sub(replace_install, js_code)
    if not matches:
        raise ValueError("'await micropip install' not found in the JS file.")
    print(f"Replaced '{lib_name}' in {matches} micropip install list(s)")
    return updated