"""쇼핑 리스트 앱 (3단계: UI 정리)

PRD.md 5장의 FR-1 ~ FR-5를 구현하고, 7·9장에 맞춰 레이아웃을 다듬었다.
동작과 검증 규칙은 2단계와 동일하다.
"""

import json
import string
from pathlib import Path

import streamlit as st

MAX_NAME_LENGTH = 50

# 목록을 저장할 파일. app.py와 같은 폴더에 둔다.
DATA_FILE = Path(__file__).with_name("items.json")

# 아이템 한 행의 컬럼 비율: [체크박스 | 이름 | 수정 | 삭제]
ROW_RATIO = [0.6, 6, 1, 1]
# 편집 모드 행: 체크박스 자리를 입력창이 흡수해 일반 행과 오른쪽 끝이 맞는다.
EDIT_ROW_RATIO = [6.6, 1, 1]

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")


# --- 저장 ------------------------------------------------------------------

def load_items():
    """저장 파일을 읽어 (items, next_id, 오류 메시지)를 돌려준다.

    파일이 없거나 내용이 깨져 있어도 예외를 밖으로 내보내지 않는다.
    그런 경우 빈 목록으로 시작하고 오류 메시지를 함께 돌려준다.
    """
    if not DATA_FILE.exists():
        return [], 1, ""

    try:
        # utf-8-sig로 읽어야 메모장 등이 붙인 BOM이 있어도 목록을 잃지 않는다.
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8-sig"))
        items = [
            {"id": int(row["id"]), "name": str(row["name"]), "done": bool(row["done"])}
            for row in raw["items"]
        ]
        next_id = int(raw["next_id"])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return [], 1, f"저장 파일을 읽지 못해 빈 목록으로 시작합니다. ({exc})"

    # next_id가 기존 id와 겹치면 위젯 key가 충돌하므로 항상 최댓값 위로 올린다.
    next_id = max([next_id] + [item["id"] + 1 for item in items])
    return items, next_id, ""


def save_items():
    """현재 목록을 저장 파일에 쓴다. 실패해도 앱은 계속 동작한다.

    임시 파일에 먼저 쓰고 교체해서, 쓰는 도중 중단돼도 기존 파일이
    반쪽짜리로 남지 않게 한다.
    """
    payload = {
        "next_id": st.session_state.next_id,
        "items": st.session_state["items"],
    }
    temp_file = DATA_FILE.with_suffix(".json.tmp")
    try:
        temp_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_file.replace(DATA_FILE)
        st.session_state.save_error = ""
    except OSError as exc:
        st.session_state.save_error = f"목록을 저장하지 못했습니다. ({exc})"


# --- 상태 ------------------------------------------------------------------

def init_state():
    """세션 상태를 처음 한 번만 초기화한다. 기존 값은 덮어쓰지 않는다.

    items는 매핑의 .items() 메서드와 이름이 겹쳐서 st.session_state.items로
    읽으면 메서드가 돌아온다. 반드시 st.session_state["items"]로 접근할 것.
    """
    if "items" not in st.session_state:
        items, next_id, load_error = load_items()
        st.session_state["items"] = items
        st.session_state.next_id = next_id
        st.session_state.load_error = load_error
    if "next_id" not in st.session_state:
        st.session_state.next_id = 1
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None
    if "save_error" not in st.session_state:
        st.session_state.save_error = ""
    if "load_error" not in st.session_state:
        st.session_state.load_error = ""


# --- 동작 ------------------------------------------------------------------

def normalize(name):
    """중복 비교용 정규화. 대소문자와 공백 차이를 무시한다."""
    return " ".join(name.split()).lower()


def escape_markdown(name):
    """아이템 이름을 마크다운 문법이 아닌 글자 그대로 보이게 만든다.

    이름은 사용자 입력이라 '1. 계란'은 번호 목록으로, '**계란**'은 굵은 글씨로
    해석돼 버린다. 완료 항목을 감싸는 :gray[...] 는 이름 안의 ']' 에서 조기에
    닫혀 취소선까지 깨진다. CommonMark는 ASCII 구두점 앞의 역슬래시를 글자
    그대로 읽으므로, 구두점을 전부 이스케이프해 둘 다 막는다.
    """
    return "".join("\\" + ch if ch in string.punctuation else ch for ch in name)


def validate_name(name, exclude_id=None):
    """이름의 유효성을 검사해 (정리된 이름, 오류 메시지)를 돌려준다.

    오류가 없으면 메시지는 빈 문자열이다.
    exclude_id에 해당하는 아이템은 중복 검사에서 제외한다(자기 자신 수정).
    """
    cleaned = name.strip()

    if not cleaned:
        return "", "아이템 이름을 입력해 주세요."

    if len(cleaned) > MAX_NAME_LENGTH:
        return "", f"이름은 {MAX_NAME_LENGTH}자까지 입력할 수 있습니다. (현재 {len(cleaned)}자)"

    target = normalize(cleaned)
    for item in st.session_state["items"]:
        if item["id"] == exclude_id:
            continue
        if normalize(item["name"]) == target:
            return "", f"'{item['name']}'은(는) 이미 목록에 있습니다."

    return cleaned, ""


def add_item(name):
    """새 아이템을 목록 맨 아래에 미완료 상태로 추가한다."""
    st.session_state["items"].append(
        {"id": st.session_state.next_id, "name": name, "done": False}
    )
    st.session_state.next_id += 1
    save_items()


def delete_item(item_id):
    """아이템을 삭제한다. 순회 중 삭제를 피하려고 새 리스트로 교체한다."""
    st.session_state["items"] = [
        item for item in st.session_state["items"] if item["id"] != item_id
    ]
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
    save_items()


def delete_done_items():
    """완료된 아이템을 모두 삭제한다."""
    done_ids = {item["id"] for item in st.session_state["items"] if item["done"]}
    st.session_state["items"] = [
        item for item in st.session_state["items"] if item["id"] not in done_ids
    ]
    if st.session_state.editing_id in done_ids:
        st.session_state.editing_id = None
    save_items()


def update_item(item_id, name):
    """아이템의 이름만 바꾼다. done 상태와 목록 순서는 유지된다."""
    for item in st.session_state["items"]:
        if item["id"] == item_id:
            item["name"] = name
            break
    save_items()


def toggle_item(item_id):
    """아이템의 완료 여부를 뒤집는다. 체크박스 on_change 콜백으로 호출된다."""
    for item in st.session_state["items"]:
        if item["id"] == item_id:
            item["done"] = not item["done"]
            break
    save_items()


def start_editing(item_id):
    st.session_state.editing_id = item_id


def stop_editing():
    st.session_state.editing_id = None


def visible_items(items, item_filter):
    if item_filter == "미완료":
        return [item for item in items if not item["done"]]
    if item_filter == "완료":
        return [item for item in items if item["done"]]
    return items


# --- 화면: 입력 -------------------------------------------------------------

init_state()

st.title("🛒 쇼핑 리스트")

if st.session_state.load_error:
    st.warning(st.session_state.load_error)
if st.session_state.save_error:
    st.error(st.session_state.save_error)

# 추가에 성공했을 때만 입력창을 비운다. 위젯 값은 생성된 뒤에는 바꿀 수 없어서,
# 직전 실행에서 세워 둔 플래그를 보고 위젯을 만들기 전에 비운다.
if st.session_state.pop("clear_new_item", False):
    st.session_state["new_item_name"] = ""

with st.form("add_item_form", clear_on_submit=False):
    input_col, button_col = st.columns([4, 1], vertical_alignment="bottom")
    typed_name = input_col.text_input(
        "아이템 입력", placeholder="아이템 입력...", label_visibility="collapsed",
        key="new_item_name",
    )
    submitted = button_col.form_submit_button(
        "추가", type="primary", use_container_width=True
    )

if submitted:
    cleaned_name, error = validate_name(typed_name)
    if error:
        # 입력한 값은 그대로 두어 51자짜리 이름을 다시 타이핑하지 않게 한다.
        st.warning(error)
    else:
        add_item(cleaned_name)
        st.session_state["clear_new_item"] = True
        st.rerun()

st.divider()


# --- 화면: 요약과 필터 -------------------------------------------------------

items = st.session_state["items"]
total = len(items)
done_count = sum(1 for item in items if item["done"])
ratio = done_count / total if total else 0.0

st.progress(ratio, text=f"완료 {done_count} / {total} ({round(ratio * 100)}%)")

item_filter = st.radio(
    "필터", ["전체", "미완료", "완료"], horizontal=True, label_visibility="collapsed"
)

st.divider()


# --- 화면: 목록 -------------------------------------------------------------

shown = visible_items(items, item_filter)

if not items:
    st.info("아직 담은 항목이 없습니다. 위에서 추가해 보세요.")
elif not shown:
    st.info("해당 조건의 항목이 없습니다.")

for item in shown:
    item_id = item["id"]

    if st.session_state.editing_id == item_id:
        edit_col, save_col, cancel_col = st.columns(
            EDIT_ROW_RATIO, vertical_alignment="center"
        )
        edited_name = edit_col.text_input(
            "이름 수정", value=item["name"], key=f"edit_input_{item_id}",
            label_visibility="collapsed",
        )
        save_clicked = save_col.button(
            "저장", key=f"save_{item_id}", type="primary",
            use_container_width=True, help="변경한 이름 저장",
        )
        cancel_col.button(
            "취소", key=f"cancel_{item_id}", on_click=stop_editing,
            use_container_width=True, help="수정 취소",
        )

        if save_clicked:
            cleaned_name, error = validate_name(edited_name, exclude_id=item_id)
            if error:
                st.warning(error)
            else:
                update_item(item_id, cleaned_name)
                stop_editing()
                st.rerun()
        continue

    check_col, name_col, edit_col, delete_col = st.columns(
        ROW_RATIO, vertical_alignment="center"
    )

    check_col.checkbox(
        item["name"], value=item["done"], key=f"chk_{item_id}",
        label_visibility="collapsed", on_change=toggle_item, args=(item_id,),
        help="구매 완료 표시",
    )

    safe_name = escape_markdown(item["name"])
    if item["done"]:
        name_col.markdown(f":gray[~~{safe_name}~~]")
    else:
        name_col.markdown(safe_name)

    edit_col.button(
        "✏️", key=f"edit_{item_id}", on_click=start_editing, args=(item_id,),
        use_container_width=True, help="이름 수정",
    )
    delete_col.button(
        "🗑", key=f"del_{item_id}", on_click=delete_item, args=(item_id,),
        type="secondary", use_container_width=True, help="삭제",
    )


# --- 화면: 하단 액션 ---------------------------------------------------------

if items:
    st.divider()
    st.button(
        "완료 항목 모두 삭제",
        disabled=done_count == 0,
        on_click=delete_done_items,
        help="체크된 항목을 한 번에 비웁니다",
    )
