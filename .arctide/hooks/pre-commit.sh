#!/usr/bin/env bash
# shellcheck disable=SC2329
set -euo pipefail

MODE="${1:---check}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

FAILURES=0

ignore_path() {
	case "$1" in
	node_modules/* | .git/* | .build/* | DerivedData/* | SourcePackages/checkouts/* | .next/* | coverage/* | dist/* | build/* | vendor/* | .swiftpm/* | .spm-cache/* | .venv/* | venv/*)
		return 0
		;;
	*)
		return 1
		;;
	esac
}

mapfile_from_cmd() {
	local __var="$1"
	shift
	local -a __items=()
	while IFS= read -r line; do
		[[ -n "$line" ]] && __items+=("$line")
	done < <("$@")
	if [[ ${#__items[@]} -eq 0 ]]; then
		eval "$__var=()"
	else
		eval "$__var=(\"\${__items[@]}\")"
	fi
}

staged_files_cmd() {
	git diff --cached --name-only --diff-filter=ACM
}

record_failure() {
	local gate="$1"
	local message="$2"
	local rerun="$3"
	FAILURES=$((FAILURES + 1))
	cat <<EOF
ERROR [$gate]
  repo: $REPO_ROOT
  message: $message
  rerun: $rerun
EOF
}

have() {
	command -v "$1" >/dev/null 2>&1
}

bootstrap_tool() {
	local tool="$1"
	local package="${2:-$1}"

	have "$tool" && return 0
	export PATH="$HOME/.local/bin:$HOME/Library/Python/3.13/bin:$HOME/Library/Python/3.12/bin:$HOME/Library/Python/3.11/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

	case "$tool" in
	ruff)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install ruff >/dev/null 2>&1 || true; fi
		if ! have ruff && have uv; then uv tool install ruff >/dev/null 2>&1 || true; fi
		if ! have ruff && have python3; then python3 -m pip install --user ruff >/dev/null 2>&1 || true; fi
		;;
	pyright)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install pyright >/dev/null 2>&1 || true; fi
		if ! have pyright && have npm; then npm install -g pyright >/dev/null 2>&1 || true; fi
		;;
	yamllint)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install yamllint >/dev/null 2>&1 || true; fi
		if ! have yamllint && have python3; then python3 -m pip install --user yamllint >/dev/null 2>&1 || true; fi
		;;
	uv)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install uv >/dev/null 2>&1 || true; fi
		if ! have uv && have curl; then curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true; fi
		;;
	node | npm)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install node >/dev/null 2>&1 || true; fi
		;;
	*)
		if have brew; then HOMEBREW_NO_AUTO_UPDATE=1 brew install "$package" >/dev/null 2>&1 || true; fi
		;;
	esac

	have "$tool"
}

ensure_tool() {
	local tool="$1"
	local package="${2:-$1}"
	local gate="${3:-$tool}"
	bootstrap_tool "$tool" "$package" && return 0
	record_failure "$gate" "required tool '$tool' is not installed and could not be bootstrapped" "brew install $package"
	return 1
}

ensure_node_dependencies() {
	[[ -f package.json ]] || return 0
	[[ -d node_modules ]] && return 0

	ensure_tool node node node >/dev/null || return 1
	ensure_tool npm node npm >/dev/null || return 1

	if [[ -f pnpm-lock.yaml ]]; then
		corepack enable >/dev/null 2>&1 || true
		if command -v pnpm >/dev/null 2>&1; then
			pnpm install --frozen-lockfile
			return $?
		fi
	elif [[ -f yarn.lock ]]; then
		corepack enable >/dev/null 2>&1 || true
		if command -v yarn >/dev/null 2>&1; then
			yarn install --frozen-lockfile
			return $?
		fi
	elif [[ -f package-lock.json ]]; then
		npm ci
		return $?
	fi

	npm install
}

collect_files() {
	local pattern="$1"
	local -a items=()
	while IFS= read -r file; do
		[[ -z "$file" ]] && continue
		ignore_path "$file" && continue
		# shellcheck disable=SC2254
		case "$file" in
		$pattern)
			[[ -f "$REPO_ROOT/$file" ]] && items+=("$file")
			;;
		esac
	done < <(staged_files_cmd)
	if [[ ${#items[@]} -gt 0 ]]; then
		printf '%s\n' "${items[@]}"
	fi
}

mapfile_from_cmd STAGED_FILES staged_files_cmd

if [[ ${#STAGED_FILES[@]} -eq 0 ]]; then
	exit 0
fi

mapfile_from_cmd SWIFT_FILES collect_files "*.swift"
mapfile_from_cmd PYTHON_FILES collect_files "*.py"
mapfile_from_cmd SHELL_FILES collect_files "*.sh"

collect_node_files() {
	while IFS= read -r file; do
		[[ -z "$file" ]] && continue
		ignore_path "$file" && continue
		case "$file" in
		*.ts | *.tsx | *.js | *.jsx | *.mjs | *.cjs | *.css | *.astro | *.json)
			[[ -f "$REPO_ROOT/$file" ]] && printf '%s\n' "$file"
			;;
		esac
	done < <(staged_files_cmd)
}

collect_yaml_files() {
	while IFS= read -r file; do
		[[ -z "$file" ]] && continue
		ignore_path "$file" && continue
		case "$file" in
		*.yml | *.yaml)
			[[ -f "$REPO_ROOT/$file" ]] && printf '%s\n' "$file"
			;;
		esac
	done < <(staged_files_cmd)
}

mapfile_from_cmd NODE_FILES collect_node_files
mapfile_from_cmd YAML_FILES collect_yaml_files

restage_files() {
	local -a files=("$@")
	[[ ${#files[@]} -eq 0 ]] && return 0
	git add -- "${files[@]}"
}

run_secret_check() {
	ensure_tool gitleaks gitleaks gitleaks || return 0
	if ! gitleaks git --pre-commit --staged --redact --no-banner >/dev/null; then
		record_failure "gitleaks" "staged secret scan failed" "gitleaks git --pre-commit --staged --redact --no-banner"
	fi
}

swift_safety_check() {
	if [[ ! -f "$REPO_ROOT/.swiftlint.yml" ]]; then
		return 0
	fi

	local pattern='force_cast|force_try|force_unwrapping|nonisolated_unsafe|unchecked_sendable|process_info_hostname|dispatch_main_sync|thread_sleep'
	if command -v rg >/dev/null 2>&1; then
		local matches
		matches="$(rg -n "swiftlint:disable.*(${pattern})" "$REPO_ROOT" --glob '*.swift' --glob '!**/.git/**' --glob '!**/.build/**' --glob '!**/DerivedData/**' 2>/dev/null || true)"
		if [[ -n "$matches" ]]; then
			printf '%s\n' "$matches"
			record_failure "swiftlint-policy" "safety lint suppressions detected" "rg -n 'swiftlint:disable.*(${pattern})' . --glob '*.swift'"
		fi
	fi
}

run_fix_mode() {
	if [[ ${#SHELL_FILES[@]} -gt 0 ]] && ensure_tool shfmt shfmt shfmt; then
		shfmt -w "${SHELL_FILES[@]}" >/dev/null 2>&1 || true
		restage_files "${SHELL_FILES[@]}"
	fi

	if [[ ${#SWIFT_FILES[@]} -gt 0 ]]; then
		if ensure_tool swiftformat swiftformat swiftformat; then
			swiftformat "${SWIFT_FILES[@]}" >/dev/null 2>&1 || true
		fi
		if [[ -f "$REPO_ROOT/.swiftlint.yml" ]] && ensure_tool swiftlint swiftlint swiftlint; then
			swiftlint lint --fix --format --force-exclude --quiet "${SWIFT_FILES[@]}" >/dev/null 2>&1 || true
		fi
		restage_files "${SWIFT_FILES[@]}"
	fi

	if [[ ${#PYTHON_FILES[@]} -gt 0 ]] && ensure_tool ruff ruff ruff; then
		ruff check --fix "${PYTHON_FILES[@]}" >/dev/null 2>&1 || true
		ruff format "${PYTHON_FILES[@]}" >/dev/null 2>&1 || true
		restage_files "${PYTHON_FILES[@]}"
	fi

	if [[ ${#NODE_FILES[@]} -gt 0 ]]; then
		ensure_node_dependencies || true
		if [[ -x "$REPO_ROOT/node_modules/.bin/biome" ]]; then
			"$REPO_ROOT/node_modules/.bin/biome" check --write --no-errors-on-unmatched --files-ignore-unknown=true "${NODE_FILES[@]}" >/dev/null 2>&1 || true
		else
			if [[ -x "$REPO_ROOT/node_modules/.bin/prettier" ]]; then
				"$REPO_ROOT/node_modules/.bin/prettier" --write "${NODE_FILES[@]}" >/dev/null 2>&1 || true
			fi
			if [[ -x "$REPO_ROOT/node_modules/.bin/eslint" ]]; then
				"$REPO_ROOT/node_modules/.bin/eslint" --fix "${NODE_FILES[@]}" >/dev/null 2>&1 || true
			fi
		fi
		restage_files "${NODE_FILES[@]}"
	fi
}

run_check_mode() {
	run_secret_check

	if [[ ${#SHELL_FILES[@]} -gt 0 ]]; then
		local file
		for file in "${SHELL_FILES[@]}"; do
			if ! bash -n "$file"; then
				record_failure "bash-syntax" "shell syntax check failed for $file" "bash -n '$file'"
			fi
		done
		if ensure_tool shellcheck shellcheck shellcheck; then
			if ! shellcheck "${SHELL_FILES[@]}"; then
				record_failure "shellcheck" "shellcheck reported issues" "shellcheck ${SHELL_FILES[*]}"
			fi
		fi
	fi

	if [[ ${#SWIFT_FILES[@]} -gt 0 ]]; then
		swift_safety_check
		if [[ -f "$REPO_ROOT/.swiftlint.yml" ]] && ensure_tool swiftlint swiftlint swiftlint; then
			if ! swiftlint lint --strict --force-exclude --quiet "${SWIFT_FILES[@]}"; then
				record_failure "swiftlint" "SwiftLint strict check failed" "swiftlint lint --strict --force-exclude ${SWIFT_FILES[*]}"
			fi
		fi
	fi

	if [[ ${#PYTHON_FILES[@]} -gt 0 ]] && ensure_tool ruff ruff ruff; then
		if ! ruff check "${PYTHON_FILES[@]}"; then
			record_failure "ruff-check" "ruff lint failed" "ruff check ${PYTHON_FILES[*]}"
		fi
		if ! ruff format --check "${PYTHON_FILES[@]}"; then
			record_failure "ruff-format" "ruff format check failed" "ruff format --check ${PYTHON_FILES[*]}"
		fi
	fi

	if [[ ${#NODE_FILES[@]} -gt 0 ]]; then
		ensure_node_dependencies || true
		if [[ -x "$REPO_ROOT/node_modules/.bin/biome" ]]; then
			if ! "$REPO_ROOT/node_modules/.bin/biome" check --no-errors-on-unmatched --files-ignore-unknown=true "${NODE_FILES[@]}"; then
				record_failure "biome" "Biome check failed" "npx @biomejs/biome check ${NODE_FILES[*]}"
			fi
		else
			if [[ -x "$REPO_ROOT/node_modules/.bin/prettier" ]]; then
				if ! "$REPO_ROOT/node_modules/.bin/prettier" --check "${NODE_FILES[@]}"; then
					record_failure "prettier" "Prettier check failed" "npx prettier --check ${NODE_FILES[*]}"
				fi
			fi
			if [[ -x "$REPO_ROOT/node_modules/.bin/eslint" ]]; then
				if ! "$REPO_ROOT/node_modules/.bin/eslint" "${NODE_FILES[@]}"; then
					record_failure "eslint" "ESLint check failed" "npx eslint ${NODE_FILES[*]}"
				fi
			fi
		fi
	fi

	if [[ ${#YAML_FILES[@]} -gt 0 ]]; then
		local -a workflow_files=()
		local file
		for file in "${YAML_FILES[@]}"; do
			[[ "$file" == .github/workflows/* ]] && workflow_files+=("$file")
		done
		if [[ ${#workflow_files[@]} -gt 0 ]] && ensure_tool actionlint actionlint actionlint; then
			if ! actionlint "${workflow_files[@]}"; then
				record_failure "actionlint" "GitHub workflow validation failed" "actionlint ${workflow_files[*]}"
			fi
		fi

		if ensure_tool yamllint yamllint yamllint; then
			if ! yamllint -f parsable "${YAML_FILES[@]}"; then
				record_failure "yamllint" "YAML validation failed" "yamllint -f parsable ${YAML_FILES[*]}"
			fi
		fi
	fi

	if ensure_tool typos typos typos; then
		local -a typo_files=()
		local file
		for file in "${STAGED_FILES[@]}"; do
			ignore_path "$file" && continue
			[[ -f "$REPO_ROOT/$file" ]] && typo_files+=("$file")
		done
		# --force-exclude makes typos honour [files] extend-exclude in
		# .typos.toml even when files are passed explicitly. Without it,
		# binary image assets get scanned and their raw bytes regularly
		# match short typo patterns.
		if [[ ${#typo_files[@]} -gt 0 ]] && ! typos --force-exclude "${typo_files[@]}"; then
			record_failure "typos" "typos found spelling issues" "typos ${typo_files[*]}"
		fi
	fi
}

case "$MODE" in
--fix)
	run_fix_mode
	;;
--check)
	run_check_mode
	;;
*)
	echo "Usage: pre-commit.sh [--fix|--check]" >&2
	exit 2
	;;
esac

if [[ "$MODE" == "--check" && "$FAILURES" -gt 0 ]]; then
	exit 1
fi

exit 0
