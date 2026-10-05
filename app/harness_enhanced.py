# app/harness_enhanced.py
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import re
import json
from datetime import datetime

class ErrorCode(Enum):
    """错误代码枚举"""
    SUCCESS = 0
    INPUT_TOO_LONG = 1001
    SENSITIVE_CONTENT = 1002
    INJECTION_DETECTED = 1003
    RATE_LIMIT_EXCEEDED = 1004
    TIMEOUT = 1005
    OUTPUT_VALIDATION_FAILED = 2001
    OUTPUT_SENSITIVE_DATA = 2002
    OUTPUT_RISK_HIGH = 2003
    AGENT_EXECUTION_ERROR = 3001
    UNKNOWN_ERROR = 9999

class HarnessError(Exception):
    """Harness异常类"""
    def __init__(self, code: ErrorCode, message: str, details: Dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class FallbackResponse:
    """降级响应"""
    def __init__(self, success: bool, data: Any = None, error: Dict = None, fallback_used: bool = False):
        self.success = success
        self.data = data
        self.error = error
        self.fallback_used = fallback_used
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "fallback_used": self.fallback_used
        }

class EnhancedHarnessConfig:
    """增强版Harness配置"""
    MAX_ITERATIONS = 5
    MAX_INPUT_LENGTH = 10000
    MAX_OUTPUT_LENGTH = 10000
    BLOCKED_KEYWORDS = [
        "密码", "银行卡", "身份证", "忽略之前", "忽略所有", "无视"
    ]
    ALLOWED_COUNTRIES = ["中国", "日本", "泰国", "新加坡"]
    ALLOWED_CITIES = ["南京", "北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "重庆", "武汉", "苏州", "长沙", "郑州", "南京", "天津", "东莞", "青岛", "沈阳", "宁波", "昆明"]
    RATE_LIMIT = 100
    REQUEST_TIMEOUT = 30
    ENABLE_FALLBACK = True  # 启用降级服务
    FALLBACK_STRATEGY = "graceful"  # graceful: 优雅降级, strict: 严格拒绝
    # 重试配置
    ENABLE_RETRY = True  # 启用重试机制
    MAX_RETRY_ATTEMPTS = 3  # 最大重试次数
    RETRY_DELAY = 1.0  # 重试延迟（秒）
    RETRY_ON_ERROR_CODES = [
        ErrorCode.TIMEOUT,
        ErrorCode.AGENT_EXECUTION_ERROR,
        ErrorCode.OUTPUT_VALIDATION_FAILED,
    ]  # 可重试的错误码

class EnhancedInputHarness:
    """增强版输入拦截器"""
    
    def __init__(self, config: EnhancedHarnessConfig):
        self.config = config
    
    def validate_input(self, user_input: str, context: Dict = None) -> Tuple[bool, str, ErrorCode]:
        """
        验证用户输入
        
        Returns:
            (is_valid, error_message, error_code)
        """
        # 1. 长度检查
        if len(user_input) > self.config.MAX_INPUT_LENGTH:
            return False, f"输入过长，最大{self.config.MAX_INPUT_LENGTH}字符", ErrorCode.INPUT_TOO_LONG
        
        # 2. 敏感词检查
        for keyword in self.config.BLOCKED_KEYWORDS:
            if keyword in user_input:
                return False, f"输入包含敏感词: {keyword}", ErrorCode.SENSITIVE_CONTENT
        
        # 3. 注入攻击检查
        injection_patterns = [
            r"忽略.*指示",
            r"忽略.*规则",
            r"你是一个.*而不是.*",
            r"系统提示.*改为.*",
            r"角色.*扮演",
            r"忽略.*之前.*所有",
        ]
        for i, pattern in enumerate(injection_patterns):
            if re.search(pattern, user_input, re.IGNORECASE):
                return False, f"检测到潜在的注入攻击 (pattern #{i})", ErrorCode.INJECTION_DETECTED
        
        # 4. 上下文相关的检查
        if context and "budget" in context:
            budget = context.get("budget", 0)
            if budget > 100000:
                return False, "预算金额超出允许范围", ErrorCode.SENSITIVE_CONTENT
        
        return True, "", ErrorCode.SUCCESS
    
    def sanitize_input(self, user_input: str) -> str:
        """清理输入"""
        # 1. Unicode规范化
        import unicodedata
        user_input = unicodedata.normalize('NFKC', user_input)
        
        # 2. 移除零宽字符
        user_input = re.sub(r"[\u200b-\u200f\ufeff]", "", user_input)
        
        # 3. 移除 bidi 字符
        user_input = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", user_input)
        
        # 4. 移除多余空白
        user_input = " ".join(user_input.split())
        
        # 5. 移除特殊控制字符
        user_input = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", user_input)
        
        # 6. 移除HTML/JS标签
        user_input = re.sub(r"<[^>]*script[^>]*>", "", user_input, flags=re.IGNORECASE)
        user_input = re.sub(r"javascript:", "", user_input, flags=re.IGNORECASE)
        user_input = re.sub(r"on\w+\s*=", "", user_input, flags=re.IGNORECASE)
        
        # 7. 移除编码攻击
        user_input = re.sub(r"\\x[0-9a-fA-F]{2}", "", user_input)
        user_input = re.sub(r"\\u[0-9a-fA-F]{4}", "", user_input)
        
        return user_input.strip()
    
    def get_input_risk_score(self, user_input: str) -> float:
        """
        计算输入风险评分
        
        Returns:
            0.0 - 1.0 的风险评分
        """
        risk_score = 0.0
        
        # 检查敏感词密度
        sensitive_count = sum(1 for kw in self.config.BLOCKED_KEYWORDS if kw in user_input)
        risk_score += min(sensitive_count * 0.2, 0.4)
        
        # 检查注入模式匹配度
        injection_patterns = [
            r"忽略.*指示",
            r"忽略.*规则",
            r"你是一个.*而不是.*",
            r"系统提示.*改为.*",
        ]
        injection_matches = sum(1 for p in injection_patterns if re.search(p, user_input))
        risk_score += min(injection_matches * 0.3, 0.6)
        
        return min(risk_score, 1.0)


class EnhancedOutputHarness:
    """增强版输出拦截器"""
    
    def __init__(self, config: EnhancedHarnessConfig):
        self.config = config
    
    def validate_output(self, output: Any, expected_type: type = None) -> Tuple[bool, str, ErrorCode]:
        """
        验证Agent输出
        
        Returns:
            (is_valid, error_message, error_code)
        """
        # 1. 输出长度检查
        if isinstance(output, str) and len(output) > self.config.MAX_OUTPUT_LENGTH:
            return False, f"输出过长，最大{self.config.MAX_OUTPUT_LENGTH}字符", ErrorCode.OUTPUT_VALIDATION_FAILED
        
        # 2. 类型检查
        if expected_type and not isinstance(output, expected_type):
            return False, f"输出类型错误，期望{expected_type}", ErrorCode.OUTPUT_VALIDATION_FAILED
        
        # 3. 结构化输出验证
        if hasattr(output, 'model_validate'):
            try:
                if hasattr(output, 'city') and not output.city:
                    return False, "输出缺少必要字段: city", ErrorCode.OUTPUT_VALIDATION_FAILED
            except Exception as e:
                return False, f"输出验证失败: {str(e)}", ErrorCode.OUTPUT_VALIDATION_FAILED
        
        return True, "", ErrorCode.SUCCESS
    
    def sanitize_output(self, output: Any) -> Any:
        """清理输出"""
        if isinstance(output, str):
            # 1. 敏感信息脱敏
            sensitive_patterns = [
                (r"\b1[3-9]\d{9}\b", "[手机号已脱敏]"),  # 手机号
                (r"\b\d{17}[\dXx]\b", "[身份证号已脱敏]"),  # 身份证
                (r"\b\d{16,19}\b", "[银行卡号已脱敏]"),  # 银行卡
                (r"\b[\w.-]+@[\w.-]+\.\w+\b", "[邮箱已脱敏]"),  # 邮箱
                (r"密码[：:\s]*[^\s,，。]{6,}", "[密码已脱敏]"),
                (r"password[：:\s]*[^\s,，。]{6,}", "[密码已脱敏]"),
                (r"\b\d{5,6}\b", "[邮编已脱敏]"),  # 邮编
            ]
            
            for pattern, replacement in sensitive_patterns:
                output = re.sub(pattern, replacement, output)
            
            # 2. 可疑链接处理
            suspicious_patterns = [
                r"\.tk[/\s]",
                r"\.ml[/\s]",
                r"\.ga[/\s]",
                r"bit\.ly",
                r"goo\.gl",
            ]
            for pattern in suspicious_patterns:
                output = re.sub(rf"https?://[^\s]*{pattern}[^\s]*", "[链接已屏蔽]", output, flags=re.IGNORECASE)
            
            # 3. 代码注入防护
            output = re.sub(r"<script[^>]*>", "[脚本已屏蔽]", output, flags=re.IGNORECASE)
            output = re.sub(r"javascript:", "[协议已屏蔽]", output, flags=re.IGNORECASE)
            output = re.sub(r"on\w+\s*=", "[事件已屏蔽]", output, flags=re.IGNORECASE)
            
            # 4. Unicode规范化
            import unicodedata
            output = unicodedata.normalize('NFKC', output)
        
        return output
    
    def risk_assessment(self, output: Any) -> Tuple[str, List[str], float]:
        """
        评估输出风险等级
        
        Returns:
            (risk_level, reasons, risk_score)
        """
        risk_level = "low"
        reasons = []
        risk_score = 0.0
        
        output_str = str(output)
        
        # 检查是否包含外部链接
        if re.search(r"https?://[^\s]+\.(com|net|org)", output_str):
            risk_level = "medium"
            reasons.append("输出包含外部链接")
            risk_score += 0.3
        
        # 检查是否包含大量个人信息
        if len(re.findall(r"\d{6,}", output_str)) > 5:
            risk_level = "high"
            reasons.append("输出包含疑似敏感数字")
            risk_score += 0.5
        
        # 检查是否包含代码注入
        if re.search(r"<script|javascript:|onerror=", output_str, re.IGNORECASE):
            risk_level = "high"
            reasons.append("检测到可能的代码注入")
            risk_score += 0.7
        
        return risk_level, reasons, min(risk_score, 1.0)


class EnhancedAgentHarness:
    """增强版Agent执行包装器"""
    
    def __init__(self, agent, config: EnhancedHarnessConfig = None):
        self.agent = agent
        self.config = config or EnhancedHarnessConfig()
        self.input_harness = EnhancedInputHarness(self.config)
        self.output_harness = EnhancedOutputHarness(self.config)
        self.execution_count = {}
        self.last_execution = {}
        self.error_counts = {}  # 错误计数

    def _record_harness_counter(self, name: str, tags: Dict = None):
        try:
            from observability import observer
            observer.record_counter(name, 1, tags or {})
        except ImportError:
            pass

    def _record_input_validation(self, session_id: str, user_input: str,
                                 is_valid: bool, error_code: ErrorCode, error_msg: str):
        try:
            from observability import security_instrumentor
            blocked_keywords = [kw for kw in self.config.BLOCKED_KEYWORDS if kw in user_input]
            injection_patterns = [error_msg] if error_code == ErrorCode.INJECTION_DETECTED else []
            security_instrumentor.record_input_validation(
                session_id=session_id,
                is_valid=is_valid,
                error_code=str(error_code.value if error_code else ""),
                error_message=error_msg,
                risk_score=self.input_harness.get_input_risk_score(user_input),
                blocked_keywords=blocked_keywords,
                injection_patterns=injection_patterns,
                input_length=len(user_input),
            )
        except ImportError:
            pass

    def _record_output_validation(self, session_id: str, output: Any, is_valid: bool,
                                  error_code: ErrorCode = ErrorCode.SUCCESS,
                                  error_msg: str = "", risk_level: str = "low",
                                  risk_score: float = 0.0, risk_reasons: List[str] = None):
        try:
            from observability import security_instrumentor
            security_instrumentor.record_output_validation(
                session_id=session_id,
                is_valid=is_valid,
                error_code=str(error_code.value if error_code else ""),
                error_message=error_msg,
                risk_level=risk_level,
                risk_score=risk_score,
                risk_reasons=risk_reasons or [],
                output_length=len(str(output)) if output is not None else 0,
            )
        except ImportError:
            pass

    def _record_retry(self, error_code: ErrorCode):
        self._record_harness_counter(
            "retry_attempts_total",
            {"harness": "agent", "error_code": str(error_code.value)},
        )

    def _record_fallback(self, context: Dict, reason: str):
        session_id = context.get("session_id", "default") if context else "default"
        self._record_harness_counter(
            "fallback_used_total",
            {"harness": "agent", "session_id": session_id, "reason": reason},
        )
    
    async def execute(self, user_input: str, context: Dict = None) -> FallbackResponse:
        """
        带Harness保护、重试机制和降级服务的Agent执行
        
        Returns:
            FallbackResponse对象
        """
        session_id = context.get("session_id", "default") if context else "default"
        self._record_harness_counter(
            "harness_executions_total",
            {"harness": "agent", "agent": self.agent.name},
        )
        
        # 导入可观测性模块
        try:
            from observability import observer, EventType
            observer.record_event(EventType.AGENT_START, {
                "agent_name": self.agent.name,
                "session_id": session_id,
                "user_input_preview": user_input[:100]
            })
        except ImportError:
            pass
        
        # ========== 前置拦截 ==========
        
        # 1. 输入验证
        is_valid, error_msg, error_code = self.input_harness.validate_input(user_input, context)
        self._record_input_validation(session_id, user_input, is_valid, error_code, error_msg)
        if not is_valid:
            self._log_error(session_id, error_code, error_msg)
            return self._handle_input_error(error_code, error_msg, context)
        
        # 2. 清理输入
        clean_input = self.input_harness.sanitize_input(user_input)
        
        # 3. 执行频率检查
        if not self._check_rate_limit(session_id):
            error_msg = "请求过于频繁，请稍后再试"
            self._log_error(session_id, ErrorCode.RATE_LIMIT_EXCEEDED, error_msg)
            self._record_harness_counter(
                "harness_rate_limit_hits_total",
                {"harness": "agent", "session_id": session_id},
            )
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.RATE_LIMIT_EXCEEDED.value, "message": error_msg}
            )
        
        # 4. 时间间隔检查
        if not self._check_time_interval(session_id):
            error_msg = "请求过于频繁，请稍后再试"
            self._log_error(session_id, ErrorCode.RATE_LIMIT_EXCEEDED, error_msg)
            self._record_harness_counter(
                "harness_rate_limit_hits_total",
                {"harness": "agent", "session_id": session_id},
            )
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.RATE_LIMIT_EXCEEDED.value, "message": error_msg}
            )
        
        # ========== Agent执行（带重试）==========
        last_error = None
        retry_count = 0
        max_attempts = self.config.MAX_RETRY_ATTEMPTS if self.config.ENABLE_RETRY else 1
        
        for attempt in range(1, max_attempts + 1):
            try:
                # 设置超时控制
                result = await self._execute_with_timeout(clean_input)
                
            except TimeoutError:
                last_error = ErrorCode.TIMEOUT
                error_msg = f"请求超时 (第{attempt}次尝试)"
                self._log_error(session_id, ErrorCode.TIMEOUT, error_msg)
                
                # 检查是否应该重试
                if self.config.ENABLE_RETRY and attempt < max_attempts:
                    retry_count += 1
                    self._record_retry(ErrorCode.TIMEOUT)
                    await self._retry_delay()
                    continue
                
                return self._handle_timeout_error(context)
                
            except Exception as e:
                last_error = ErrorCode.AGENT_EXECUTION_ERROR
                error_msg = f"Agent执行失败 (第{attempt}次尝试): {str(e)}"
                self._log_error(session_id, ErrorCode.AGENT_EXECUTION_ERROR, error_msg)
                
                # 检查是否应该重试
                if self.config.ENABLE_RETRY and attempt < max_attempts:
                    retry_count += 1
                    self._record_retry(ErrorCode.AGENT_EXECUTION_ERROR)
                    await self._retry_delay()
                    continue
                
                return self._handle_execution_error(e, context)
            
            # 执行成功，跳出重试循环
            break
        
        # ========== 后置拦截 ==========
        
        # 1. 输出验证
        is_valid, error_msg, error_code = self.output_harness.validate_output(result)
        if not is_valid:
            self._log_error(session_id, error_code, error_msg)
            self._record_output_validation(
                session_id,
                result,
                is_valid=False,
                error_code=error_code,
                error_msg=error_msg,
                risk_level="validation_failed",
            )
            
            # 检查是否应该重试输出验证失败
            if self.config.ENABLE_RETRY and retry_count < max_attempts - 1:
                retry_count += 1
                self._record_retry(error_code)
                self._log_error(session_id, error_code, f"输出验证失败，尝试重试 (第{retry_count + 1}次)")
                await self._retry_delay()
                # 重新执行Agent
                return await self.execute(user_input, context)
            
            return FallbackResponse(
                success=False,
                error={"code": error_code.value, "message": error_msg}
            )
        
        # 2. 清理输出
        clean_output = self.output_harness.sanitize_output(result)
        
        # 3. 风险评估
        risk_level, reasons, risk_score = self.output_harness.risk_assessment(clean_output)
        
        if risk_level == "high":
            self._log_error(session_id, ErrorCode.OUTPUT_RISK_HIGH, f"高风险输出: {reasons}")
            self._record_output_validation(
                session_id,
                clean_output,
                is_valid=False,
                error_code=ErrorCode.OUTPUT_RISK_HIGH,
                error_msg="High risk output",
                risk_level=risk_level,
                risk_score=risk_score,
                risk_reasons=reasons,
            )
            
            # 检查是否应该重试高风险输出
            if self.config.ENABLE_RETRY and retry_count < max_attempts - 1:
                retry_count += 1
                self._record_retry(ErrorCode.OUTPUT_RISK_HIGH)
                self._log_error(session_id, ErrorCode.OUTPUT_RISK_HIGH, f"高风险输出，尝试重试 (第{retry_count + 1}次)")
                await self._retry_delay()
                # 重新执行Agent
                return await self.execute(user_input, context)
            
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.OUTPUT_RISK_HIGH.value, "message": "输出内容存在风险，已被拦截"}
            )
        
        # 4. 审计日志
        self._log_success(session_id, clean_input, clean_output, risk_level, retry_count)
        self._record_output_validation(
            session_id,
            clean_output,
            is_valid=True,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_reasons=reasons,
        )
        
        # 记录Agent执行完成事件
        try:
            from observability import observer, EventType
            observer.record_event(EventType.AGENT_COMPLETE, {
                "agent_name": self.agent.name,
                "session_id": session_id,
                "risk_level": risk_level,
                "retry_count": retry_count
            })
        except ImportError:
            pass
        
        return FallbackResponse(
            success=True,
            data=clean_output
        )
    
    async def _retry_delay(self):
        """重试延迟"""
        import asyncio
        await asyncio.sleep(self.config.RETRY_DELAY)
    
    def _check_rate_limit(self, session_id: str) -> bool:
        """检查频率限制"""
        self.execution_count[session_id] = self.execution_count.get(session_id, 0) + 1
        return self.execution_count[session_id] <= self.config.RATE_LIMIT
    
    def _check_time_interval(self, session_id: str) -> bool:
        """检查时间间隔"""
        current_time = datetime.now().timestamp()
        last_time = self.last_execution.get(session_id, 0)
        if current_time - last_time < 0.5:
            return False
        self.last_execution[session_id] = current_time
        return True
    
    async def _execute_with_timeout(self, user_input: str, timeout: int = None) -> Any:
        """带超时控制的执行"""
        import asyncio
        
        timeout = timeout or self.config.REQUEST_TIMEOUT
        
        try:
            result = await asyncio.wait_for(
                self.agent.run(user_input),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError()
    
    def _handle_input_error(self, error_code: ErrorCode, error_msg: str, context: Dict) -> FallbackResponse:
        """处理输入错误"""
        # 根据配置决定是拒绝还是降级
        if self.config.ENABLE_FALLBACK and self.config.FALLBACK_STRATEGY == "graceful":
            self._record_fallback(context, f"input_error_{error_code.value}")
            # 优雅降级：返回部分信息
            return FallbackResponse(
                success=True,
                data=self._generate_fallback_response(context),
                error={"code": error_code.value, "message": error_msg},
                fallback_used=True
            )
        else:
            # 严格拒绝
            return FallbackResponse(
                success=False,
                error={"code": error_code.value, "message": error_msg}
            )
    
    def _handle_timeout_error(self, context: Dict) -> FallbackResponse:
        """处理超时错误"""
        if self.config.ENABLE_FALLBACK:
            self._record_fallback(context, "timeout")
            return FallbackResponse(
                success=True,
                data=self._generate_fallback_response(context),
                error={"code": ErrorCode.TIMEOUT.value, "message": "请求超时，已返回缓存结果"},
                fallback_used=True
            )
        else:
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.TIMEOUT.value, "message": "请求超时，请稍后重试"}
            )
    
    def _handle_execution_error(self, error: Exception, context: Dict) -> FallbackResponse:
        """处理执行错误"""
        # 记录错误次数
        session_id = context.get("session_id", "default") if context else "default"
        self.error_counts[session_id] = self.error_counts.get(session_id, 0) + 1
        
        if self.config.ENABLE_FALLBACK and self.error_counts[session_id] <= 3:
            self._record_fallback(context, "execution_error")
            # 首次错误，尝试降级
            return FallbackResponse(
                success=True,
                data=self._generate_fallback_response(context),
                error={"code": ErrorCode.AGENT_EXECUTION_ERROR.value, "message": "服务暂时不可用，已返回备选结果"},
                fallback_used=True
            )
        else:
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.AGENT_EXECUTION_ERROR.value, "message": "处理您的请求时发生错误，请稍后重试"}
            )
    
    def _generate_fallback_response(self, context: Dict) -> Dict:
        """生成降级响应"""
        # 返回一个基础的、友好的响应
        return {
            "type": "fallback",
            "message": "抱歉，系统正在处理您的请求，请稍后再试。",
            "suggestion": "您可以尝试简化您的请求，或者稍后再试。"
        }
    
    def _log_error(self, session_id: str, error_code: ErrorCode, message: str):
        """记录错误日志"""
        print(f"[ERROR] session={session_id} code={error_code.value} msg={message}")
    
    def _log_success(self, session_id: str, input_text: str, output: Any, risk_level: str, retry_count: int = 0):
        """记录成功日志"""
        print(f"[SUCCESS] session={session_id} risk={risk_level} retries={retry_count}")


class EnhancedParallelPlannerHarness:
    """增强版并行规划器的Harness"""
    
    def __init__(self, parallel_planner, config: EnhancedHarnessConfig = None):
        self.parallel_planner = parallel_planner
        self.config = config or EnhancedHarnessConfig()
        self.input_harness = EnhancedInputHarness(self.config)
    
    async def create_plan_optimized(self, request, context: Dict = None) -> FallbackResponse:
        """带Harness保护和重试机制的并行规划"""
        session_id = context.get("session_id", "default") if context else "default"
        memory_context = context.get("memory_context", "") if context else ""
        try:
            from observability import observer
            observer.record_counter(
                "harness_executions_total",
                1,
                {"harness": "parallel_planner"},
            )
        except ImportError:
            pass
        
        # 记录规划开始事件
        try:
            from observability import observer, EventType
            observer.record_event(EventType.PLANNING_START, {
                "session_id": session_id,
                "city": request.city,
                "travel_days": request.travel_days
            })
        except ImportError:
            pass
        
        # 1. 输入验证
        request_dict = request.model_dump()
        # 取消城市白名单限制，所有城市都可规划
        # if request.city not in self.config.ALLOWED_CITIES:
        #     error_msg = f"目的地 {request.city} 暂不支持"
        #     return FallbackResponse(
        #         success=False,
        #         error={"code": ErrorCode.SENSITIVE_CONTENT.value, "message": error_msg}
        #     )
        
        # 2. 检查预算合理性
        if hasattr(request, 'budget') and request.budget and request.budget.total > 100000:
            error_msg = "预算金额超出允许范围"
            return FallbackResponse(
                success=False,
                error={"code": ErrorCode.SENSITIVE_CONTENT.value, "message": error_msg}
            )
        
        # 3. 执行并行规划（带重试）
        max_attempts = self.config.MAX_RETRY_ATTEMPTS if self.config.ENABLE_RETRY else 1
        
        for attempt in range(1, max_attempts + 1):
            try:
                result = await self.parallel_planner.create_plan_optimized(
                    request,
                    memory_context=memory_context,
                )
                
                # 记录规划完成事件
                try:
                    from observability import observer, EventType
                    observer.record_event(EventType.PLANNING_COMPLETE, {
                        "session_id": session_id,
                        "city": request.city,
                        "travel_days": request.travel_days,
                        "days_planned": len(result.days) if hasattr(result, 'days') else 0
                    })
                except ImportError:
                    pass
                
                return FallbackResponse(
                    success=True,
                    data=result
                )
            except Exception as e:
                error_msg = f"并行规划失败 (第{attempt}次尝试): {str(e)}"
                print(f"[ERROR] {error_msg}")
                
                # 检查是否应该重试
                if self.config.ENABLE_RETRY and attempt < max_attempts:
                    try:
                        from observability import observer
                        observer.record_counter(
                            "retry_attempts_total",
                            1,
                            {"harness": "parallel_planner", "error_code": str(ErrorCode.AGENT_EXECUTION_ERROR.value)},
                        )
                    except ImportError:
                        pass
                    await self._retry_delay()
                    continue
                
                return FallbackResponse(
                    success=False,
                    error={"code": ErrorCode.AGENT_EXECUTION_ERROR.value, "message": f"规划失败，已重试{attempt}次"}
                )
    
    async def _retry_delay(self):
        """重试延迟"""
        import asyncio
        await asyncio.sleep(self.config.RETRY_DELAY)
