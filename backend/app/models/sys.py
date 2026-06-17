"""sys schema: 用户/角色/菜单/权限/配置表"""
from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, BigInteger,
    ForeignKey, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class SysUser(Base):
    __tablename__ = "sys_user"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True, comment="登录名")
    password_hash = Column(String(256), nullable=False, comment="bcrypt哈希密码")
    real_name = Column(String(64), comment="真实姓名")
    phone = Column(String(20), comment="手机号（脱敏存储）")
    email = Column(String(128), comment="邮箱")
    dept_id = Column(BigInteger, ForeignKey("sys.sys_department.id"), comment="部门ID")
    store_code = Column(String(32), comment="关联门店编码（店长/导购专用）")
    avatar = Column(String(512), comment="头像URL")
    status = Column(Integer, default=1, comment="1启用 0禁用")
    is_admin = Column(Boolean, default=False, comment="超级管理员标志")
    dingtalk_user_id = Column(String(64), comment="钉钉用户ID")
    dingtalk_union_id = Column(String(128), comment="钉钉unionId")
    last_login_at = Column(DateTime(timezone=True), comment="最后登录时间")
    must_change_password = Column(Boolean, default=False, comment="首次登录必须改密")
    last_login_ip = Column(String(64), comment="最后登录IP")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False, comment="软删除")

    roles = relationship("SysUserRole", back_populates="user", lazy="select")
    department = relationship("SysDepartment", back_populates="users", lazy="select")


class SysDepartment(Base):
    __tablename__ = "sys_department"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, comment="部门名称")
    parent_id = Column(BigInteger, ForeignKey("sys.sys_department.id"), comment="上级部门")
    sort_order = Column(Integer, default=0)
    status = Column(Integer, default=1)
    dingtalk_dept_id = Column(String(64), comment="钉钉部门ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship("SysUser", back_populates="department", lazy="select")


class SysRole(Base):
    __tablename__ = "sys_role"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, comment="角色名称")
    code = Column(String(64), nullable=False, unique=True, comment="角色编码")
    description = Column(String(256), comment="描述")
    data_scope = Column(String(32), default="self",
                        comment="数据范围: all/company/dept/store/self")
    status = Column(Integer, default=1)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    permissions = relationship("SysRolePermission", back_populates="role", lazy="select")
    users = relationship("SysUserRole", back_populates="role", lazy="select")


class SysMenu(Base):
    __tablename__ = "sys_menu"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_id = Column(BigInteger, default=0, comment="父菜单ID，0=根")
    name = Column(String(64), nullable=False, comment="菜单名称")
    path = Column(String(256), comment="路由路径")
    component = Column(String(256), comment="前端组件路径")
    icon = Column(String(64), comment="图标")
    menu_type = Column(String(16), default="menu", comment="menu/button/api")
    permission_code = Column(String(128), comment="权限码")
    sort_order = Column(Integer, default=0)
    is_hidden = Column(Boolean, default=False)
    status = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SysPermission(Base):
    __tablename__ = "sys_permission"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(128), nullable=False, unique=True, comment="权限码")
    name = Column(String(64), nullable=False, comment="权限名称")
    module = Column(String(64), comment="所属模块")
    description = Column(String(256))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SysUserRole(Base):
    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id"),
        {"schema": "sys"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("sys.sys_user.id"), nullable=False)
    role_id = Column(BigInteger, ForeignKey("sys.sys_role.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("SysUser", back_populates="roles")
    role = relationship("SysRole", back_populates="users")


class SysRolePermission(Base):
    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id"),
        {"schema": "sys"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    role_id = Column(BigInteger, ForeignKey("sys.sys_role.id"), nullable=False)
    permission_id = Column(BigInteger, ForeignKey("sys.sys_permission.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role = relationship("SysRole", back_populates="permissions")


class SysFieldPermission(Base):
    """字段级权限控制"""
    __tablename__ = "sys_field_permission"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    role_id = Column(BigInteger, ForeignKey("sys.sys_role.id"), nullable=False)
    module = Column(String(64), nullable=False, comment="模块名")
    field_name = Column(String(128), nullable=False, comment="字段名")
    can_view = Column(Boolean, default=False, comment="是否可见")
    mask_rule = Column(String(64), comment="脱敏规则: phone/idcard/cost/cash/none")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SysDingtalkBind(Base):
    """钉钉用户绑定"""
    __tablename__ = "sys_dingtalk_bind"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("sys.sys_user.id"), nullable=False)
    dingtalk_user_id = Column(String(64), nullable=False, unique=True)
    dingtalk_union_id = Column(String(128))
    dingtalk_name = Column(String(64))
    is_active = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=True, comment="是否允许接收推送")
    bound_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SysDict(Base):
    """数据字典"""
    __tablename__ = "sys_dict"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dict_type = Column(String(64), nullable=False, comment="字典类型")
    dict_code = Column(String(64), nullable=False, comment="字典编码")
    dict_label = Column(String(128), nullable=False, comment="字典标签")
    dict_value = Column(String(256), comment="字典值")
    sort_order = Column(Integer, default=0)
    status = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("dict_type", "dict_code"),
        {"schema": "sys"},
    )


class SysIntegrationConfig(Base):
    """外部系统集成配置"""
    __tablename__ = "sys_integration_config"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    system_code = Column(String(32), nullable=False, unique=True,
                         comment="baison/kingdee/dingtalk")
    system_name = Column(String(64), nullable=False)
    config_json = Column(JSON, comment="配置JSON，不含密钥")
    status = Column(String(16), default="excel",
                    comment="excel=手工导入 api=接口对接 disabled=禁用")
    last_sync_at = Column(DateTime(timezone=True), comment="最后同步时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SysParam(Base):
    """系统参数"""
    __tablename__ = "sys_param"
    __table_args__ = {"schema": "sys"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    param_key = Column(String(128), nullable=False, unique=True)
    param_value = Column(Text)
    description = Column(String(256))
    is_system = Column(Boolean, default=False, comment="系统参数不允许删除")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
