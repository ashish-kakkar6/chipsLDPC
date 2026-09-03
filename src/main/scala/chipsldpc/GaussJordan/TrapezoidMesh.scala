package chipsldpc.GaussJordan

import chisel3._
import chisel3.util.Cat

final case class TrapezoidMeshConfig(
    n: Int,
    liftedCols: Int,
    reduceHopDelay: Int,
    exposeFullState: Boolean = true,
) {
  require(n > 0, "n must be positive")
  require(liftedCols > 0, "liftedCols must be positive")
  require(reduceHopDelay > 0, "reduceHopDelay must be positive")

  val totalCols: Int = n + liftedCols
}

final class TrapezoidMeshIO(config: TrapezoidMeshConfig) extends Bundle {
  val clk              = Input(Clock())
  val rst              = Input(Bool())
  val en_i             = Input(Bool())
  val reduce_i         = Input(Bool())
  val data_top_i       = Input(UInt(config.totalCols.W))
  val data_bottom_o    = Output(UInt(config.liftedCols.W))
  val diag_data_out_o  = Output(UInt(config.n.W))
  val diag_reduce_in_o = Output(UInt(config.n.W))
  val diag_state_o     = Output(UInt(config.n.W))
  val a_regs_flat_o    = Output(UInt((if (config.exposeFullState) config.n * config.n else 1).W))
  val b_regs_flat_o    = Output(UInt((if (config.exposeFullState) config.n * config.liftedCols else 1).W))
}

/** Structural binary Gauss-Jordan mesh with the legacy flat SystemVerilog ABI. */
final class TrapezoidMesh(config: TrapezoidMeshConfig) extends RawModule {
  override def desiredName: String = "trapeziod_mesh"

  val io = FlatIO(new TrapezoidMeshIO(config))

  private val dataDown = Wire(Vec(config.n, Vec(config.totalCols, Bool())))
  private val opBus = Wire(Vec(config.n, Vec(config.totalCols, GjOpcode())))
  private val states = if (config.exposeFullState)
    Some(Wire(Vec(config.n, Vec(config.totalCols, Bool())))) else None
  private val diagState = Wire(Vec(config.n, Bool()))
  private val reduceIn = Wire(Vec(config.n, Bool()))
  private val reduceOut = Wire(Vec(config.n, Bool()))

  for (row <- 0 until config.n; col <- 0 until config.totalCols) {
    if (col < row) {
      dataDown(row)(col) := false.B
      opBus(row)(col) := GjOpcode.Pass
      states.foreach(_(row)(col) := false.B)
    } else if (col == row) {
      val cell = Module(new PeDiag)
      cell.clk := io.clk
      cell.rst := io.rst
      cell.en_i := io.en_i
      cell.data_i := (if (row == 0) io.data_top_i(col) else dataDown(row - 1)(col))
      cell.reduce_sig_i := reduceIn(row)
      dataDown(row)(col) := cell.data_o
      opBus(row)(col) := cell.op_o
      states.foreach(_(row)(col) := cell.state_o)
      diagState(row) := cell.state_o
      reduceOut(row) := cell.reduce_sig_o
    } else {
      val cell = Module(new PeCol)
      cell.clk := io.clk
      cell.rst := io.rst
      cell.en_i := io.en_i
      cell.data_i := (if (row == 0) io.data_top_i(col) else dataDown(row - 1)(col))
      cell.op_i := opBus(row)(col - 1)
      dataDown(row)(col) := cell.data_o
      opBus(row)(col) := cell.op_o
      states.foreach(_(row)(col) := cell.state_o)
    }
  }

  reduceIn(0) := io.reduce_i
  for (row <- 1 until config.n) {
    val pipe = withClockAndReset(io.clk, io.rst) {
      RegInit(VecInit(Seq.fill(config.reduceHopDelay)(false.B)))
    }
    when(io.en_i) {
      pipe(0) := reduceOut(row - 1)
      for (stage <- 1 until config.reduceHopDelay) {
        pipe(stage) := pipe(stage - 1)
      }
    }
    reduceIn(row) := pipe.last
  }

  private def pack(bits: Seq[Bool]): UInt = Cat(bits.reverse)

  io.data_bottom_o := pack((0 until config.liftedCols).map(col => dataDown(config.n - 1)(config.n + col)))
  io.diag_data_out_o := pack((0 until config.n).map(row => dataDown(row)(row)))
  io.diag_reduce_in_o := pack(reduceIn.toSeq)
  io.diag_state_o := pack(diagState.toSeq)
  io.a_regs_flat_o := states.fold(0.U)(grid =>
    pack(for (row <- 0 until config.n; col <- 0 until config.n) yield grid(row)(col)))
  io.b_regs_flat_o := states.fold(0.U)(grid => pack(
    for (row <- 0 until config.n; col <- 0 until config.liftedCols) yield grid(row)(config.n + col)
  ))
}
