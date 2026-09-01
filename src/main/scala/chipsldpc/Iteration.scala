package chipsldpc

import chisel3._

/** One registered CNU phase followed by one registered VNU phase for H = [[1,1],[1,1]]. */
final class MinSumIteration2x2(q: Quantization, scale: CheckScale) extends Module {
  private val checkConfig = CheckConfig(2, q, scale)
  private val variableConfig = VariableConfig(2, q)

  val io = IO(new Bundle {
    val valid      = Input(Bool())
    val syndrome   = Input(Vec(2, Bool()))
    val v2c        = Input(Vec(2, Vec(2, new SignMag(q.magnitudeBits))))
    val prior      = Input(Vec(2, SInt(q.accumulatorBits.W)))
    val outValid   = Output(Bool())
    val result     = Output(Vec(2, new VariableResult(variableConfig)))
    val nextV2C    = Output(Vec(2, Vec(2, new SignMag(q.magnitudeBits))))
  })

  private val checks = Seq.fill(2)(Module(new CheckNodeUnit(checkConfig)))
  checks.zipWithIndex.foreach { case (check, i) =>
    check.io.valid := io.valid
    check.io.inputs := io.v2c(i)
    check.io.syndrome := io.syndrome(i)
    check.io.scaleShift := 0.U
  }

  private val prior = RegInit(VecInit(Seq.fill(2)(0.S(q.accumulatorBits.W))))
  when(io.valid) { prior := io.prior }

  private val variables = Seq.fill(2)(Module(new VariableNodeUnit(variableConfig)))
  variables.zipWithIndex.foreach { case (variable, j) =>
    variable.io.valid := checks.map(_.io.outValid).reduce(_ && _)
    variable.io.prior := prior(j)
    variable.io.inputs.zipWithIndex.foreach { case (message, i) =>
      message.minima := checks(i).io.result.minima
      message.sign := checks(i).io.result.edges(j).sign
      message.useSecond := checks(i).io.result.edges(j).useSecond
    }
    io.result(j) := variable.io.result
  }

  io.outValid := variables.map(_.io.outValid).reduce(_ && _)
  io.nextV2C.zipWithIndex.foreach { case (row, i) =>
    row.zipWithIndex.foreach { case (message, j) => message := variables(j).io.result.extrinsic(i) }
  }
}
