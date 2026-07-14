from pathlib import Path


TASK_API = Path("app/api/v1/task.py")


def test_disabled_roles_do_not_grant_task_permissions():
    source = TASK_API.read_text(encoding="utf-8")
    role_codes = source[source.index("async def _role_codes"):source.index("async def _require_manager")]
    assert "SysRole.status == 1" in role_codes
    deps = Path("app/api/v1/deps.py").read_text(encoding="utf-8")
    assert deps.count("SysRole.status == 1") >= 2


def test_manager_mutations_lock_only_tasks_inside_the_users_data_scope():
    source = TASK_API.read_text(encoding="utf-8")
    assert "async def _locked_scoped_task" in source
    assert source.count("await _locked_scoped_task(db, current_user, task_id)") >= 5
    assert "SysUser.dept_id == user.dept_id" in source


def test_role_tasks_use_creator_store_when_related_store_is_missing():
    source = TASK_API.read_text(encoding="utf-8")
    assert "effective_store_code" in source
    assert "func.coalesce(AppActionTask.related_store_code" in source
    assert "AppActionTask.related_store_code.is_(None)" not in source[source.index("async def _scoped_task_statement"):source.index("def _task_capabilities")]


def test_create_and_confirm_validate_target_store_and_assignee_scope():
    source = TASK_API.read_text(encoding="utf-8")
    assert "async def _validate_assignment_scope" in source
    assert source.count("await _validate_assignment_scope(") >= 2
    assert "SysUserStore" in source
    assert "assignee.dept_id != user.dept_id" in source


def test_store_scoped_role_confirmation_requires_one_effective_store():
    source = TASK_API.read_text(encoding="utf-8")
    assert "async def _resolve_role_assignment_store" in source
    helper = source[source.index("async def _resolve_role_assignment_store"):source.index("def _task_item")]
    assert "SysUserStore.store_code" in helper
    assert "按门店分派责任角色时必须指定唯一门店" in helper
    confirm = source[source.index("async def confirm_task"):source.index("async def submit_feedback")]
    assert "await _resolve_role_assignment_store(" in confirm
    assert "if task.assignee_id is None:" in confirm


def test_source_idempotency_lookup_does_not_leak_out_of_scope_task_ids():
    source = TASK_API.read_text(encoding="utf-8")
    create = source[source.index("async def create_task"):source.index("async def get_task_detail")]
    helper = source[source.index("async def _scoped_source_task"):source.index("async def get_task_list")]
    assert "await _scoped_task_statement(db, current_user)" in helper
    assert create.count("await _scoped_source_task(") >= 2
    assert "该来源已有任务" in create
    assert "code=409" in create


def test_department_store_candidates_only_use_active_whitelisted_users():
    source = TASK_API.read_text(encoding="utf-8")
    helper = source[source.index("async def _validate_assignment_scope"):source.index("async def _resolve_role_assignment_store")]
    assert "SysUser.status == 1" in helper
    assert "SysUser.is_deleted.is_(False)" in helper
    assert "candidate_stores.intersection(scope.store_codes)" in helper
