from typing import TypeVar, List, Tuple, Optional, Any

T = TypeVar("T")


class Expr:
	def __init__(self):
		pass

class ExprLit(Expr):
	def __init__(self, s: Any):
		super().__init__()
		self.s: Any = s

class ExprID(Expr):
	def __init__(self, s: str):
		super().__init__()
		self.s: str = s

class ExprConcat(Expr):
	def __init__(self, pieces: List[Expr]):
		super().__init__()
		self.pieces: List[Expr] = pieces

class ExprField(Expr):
	def __init__(self, obj: Expr, field: str):
		super().__init__()
		self.obj: Expr = obj
		self.field: str = field

class ExprCall(Expr):
	def __init__(self, func: str, args: List[Expr]):
		super().__init__()
		self.func: str = func
		self.args: List[Expr] = args


class Stmt:
	def __init__(self, location: Tuple[int, int]):
		self.location: Tuple[int, int] = location

class StmtSequence(Stmt):
	def __init__(self, location: Tuple[int, int]):
		super().__init__(location)
		self.stmts: List[Stmt] = []

class StmtFace(Stmt):
	def __init__(self, location: Tuple[int, int], stmt: Stmt):
		super().__init__(location)
		self.stmt: Stmt = stmt

class StmtSetName(Stmt):
	def __init__(self, location: Tuple[int, int], value: Expr):
		super().__init__(location)
		self.value: Expr = value

class StmtSetDescription(Stmt):
	def __init__(self, location: Tuple[int, int], value: Expr):
		super().__init__(location)
		self.value: Expr = value

class StmtDrawText(Stmt):
	def __init__(self, location: Tuple[int, int], x: Expr, y: Expr, width: Expr, height: Expr, style: Expr, text: Expr):
		super().__init__(location)
		self.x: Expr = x
		self.y: Expr = y
		self.width: Expr = width
		self.height: Expr = height
		self.style: Expr = style
		self.text: Expr = text

class StmtDrawRect(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			x: Expr,
			y: Expr,
			width: Expr,
			height: Expr,
			color: Optional[Expr],
			line_color: Optional[Expr],
			line_width: Optional[Expr]
	):
		super().__init__(location)
		self.x: Expr = x
		self.y: Expr = y
		self.width: Expr = width
		self.height: Expr = height
		self.color: Optional[Expr] = color
		self.line_color: Optional[Expr] = line_color
		self.line_width: Optional[Expr] = line_width

class StmtDrawImage(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			x: Expr,
			y: Expr,
			src: Expr,
			align_x: Optional[Expr],
			align_y: Optional[Expr]
	):
		super().__init__(location)
		self.x: Expr = x
		self.y: Expr = y
		self.src: Expr = src
		self.align_x: Optional[Expr] = align_x
		self.align_y: Optional[Expr] = align_y

class StmtForEach(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			var: str,
			in_expr: Expr,
			body: StmtSequence
	):
		super().__init__(location)
		self.var: str = var
		self.in_expr: Expr = in_expr
		self.body: StmtSequence = body

class StmtIf(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			condition: Expr,
			body: StmtSequence
	):
		super().__init__(location)
		self.condition: Expr = condition
		self.body: StmtSequence = body

class StmtWhile(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			condition: Expr,
			body: StmtSequence
	):
		super().__init__(location)
		self.condition: Expr = condition
		self.body: StmtSequence = body

class StmtFor(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			var: str,
			kfrom: Expr,
			kto: Expr,
			step: Optional[Expr],
			body: StmtSequence
	):
		super().__init__(location)
		self.var: str = var
		self.kfrom: Expr = kfrom
		self.kto: Expr = kto
		self.step: Optional[Expr] = step
		self.body: StmtSequence = body

class WhenBlock:
	def __init__(
			self,
			location: Tuple[int, int],
			condition: Expr,
			body: StmtSequence
	):
		self.location: Tuple[int, int] = location
		self.condition: Expr = condition
		self.body: StmtSequence = body

class StmtCase(Stmt):
	def __init__(
			self,
			location: Tuple[int, int]
	):
		super().__init__(location)
		self.whens: List[WhenBlock] = []
		self.kelse: Optional[StmtSequence] = None

class StmtSetVar(Stmt):
	def __init__(
			self,
			location: Tuple[int, int],
			var: str,
			value: Expr
	):
		super().__init__(location)
		self.var: str = var
		self.value: Expr = value