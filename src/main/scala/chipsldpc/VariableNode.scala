package chipsldpc

import chisel3._
import chisel3.util.Cat

object VariableLogic {
  final case class Result(marginal: SInt, decision: Bool, extrinsic: Seq[(Bool, UInt)])

  def apply(inputs: Seq[CheckMessage], prior: SInt, config: VariableConfig): Result = {
    require(inputs.size == config.degree)
    val messages = inputs.map { input =>
      val magnitude = Mux(input.useSecond, input.minima.second, input.minima.first)
      val packed = Wire(new SignMag(config.q.magnitudeBits))
      packed.sign := input.sign
      packed.magnitude := magnitude
      Arithmetic.fromSignMag(packed, config.q.accumulatorBits)
    }
    val total = Arithmetic.sum(prior +: messages, config.workBits)
    val extrinsic = messages.map { message =>
      Arithmetic.toSignMag(total -% message.pad(config.workBits), config.q.magnitudeBits)
    }
    Result(
      Arithmetic.clipSigned(total, config.q.accumulatorBits),
      Arithmetic.hardDecision(total),
      extrinsic,
    )
  }

  def connect(output: VariableResult, result: Result): Unit = {
    output.marginal := result.marginal
    output.decision := result.decision
    output.extrinsic.zip(result.extrinsic).foreach { case (port, (sign, magnitude)) =>
      port.sign := sign
      port.magnitude := magnitude
    }
  }
}

object RelayBiasLogic {
  def apply(prior: SInt, previous: SInt, beta: UInt, q: Quantization, format: RelayFormat): SInt = {
    val betaSigned = Cat(0.U(1.W), beta).asSInt
    val scaledPrior = (prior * betaSigned) >> format.fractionalBits
    val scaledPrevious = (previous * betaSigned) >> format.fractionalBits
    val workBits = q.accumulatorBits + format.betaBits + 3
    val mixed = (scaledPrior.pad(workBits) +% previous.pad(workBits)) -% scaledPrevious.pad(workBits)
    Arithmetic.clipSigned(mixed, q.accumulatorBits)
  }
}

final class VariableNode(config: VariableConfig) extends RawModule {
  val inputs = IO(Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits))))
  val prior  = IO(Input(SInt(config.q.accumulatorBits.W)))
  val result = IO(Output(new VariableResult(config)))
  VariableLogic.connect(result, VariableLogic(inputs.toSeq, prior, config))
}

final class RelayVariableNode(config: VariableConfig, format: RelayFormat) extends RawModule {
  val inputs           = IO(Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits))))
  val prior            = IO(Input(SInt(config.q.accumulatorBits.W)))
  val previousMarginal = IO(Input(SInt(config.q.accumulatorBits.W)))
  val beta             = IO(Input(UInt(format.betaBits.W)))
  val bias             = IO(Output(SInt(config.q.accumulatorBits.W)))
  val result           = IO(Output(new VariableResult(config)))

  bias := RelayBiasLogic(prior, previousMarginal, beta, config.q, format)
  VariableLogic.connect(result, VariableLogic(inputs.toSeq, bias, config))
}

final class VariableNodeUnit(config: VariableConfig) extends Module {
  val io = IO(new Bundle {
    val valid    = Input(Bool())
    val inputs   = Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits)))
    val prior    = Input(SInt(config.q.accumulatorBits.W))
    val outValid = Output(Bool())
    val result   = Output(new VariableResult(config))
  })

  private val core = Module(new VariableNode(config))
  core.inputs := io.inputs
  core.prior := io.prior
  private val result = RegInit(0.U.asTypeOf(new VariableResult(config)))
  when(io.valid) { result := core.result }
  io.result := result
  io.outValid := RegNext(io.valid, false.B)
}

final class RelayVariableNodeUnit(config: VariableConfig, format: RelayFormat) extends Module {
  val io = IO(new Bundle {
    val valid      = Input(Bool())
    val initialize = Input(Bool())
    val inputs     = Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits)))
    val prior      = Input(SInt(config.q.accumulatorBits.W))
    val beta       = Input(UInt(format.betaBits.W))
    val outValid   = Output(Bool())
    val state      = Output(SInt(config.q.accumulatorBits.W))
    val result     = Output(new VariableResult(config))
  })

  private val previous = RegInit(0.S(config.q.accumulatorBits.W))
  private val core = Module(new RelayVariableNode(config, format))
  core.inputs := io.inputs
  core.prior := io.prior
  core.previousMarginal := Mux(io.initialize, io.prior, previous)
  core.beta := io.beta

  private val result = RegInit(0.U.asTypeOf(new VariableResult(config)))
  when(io.valid) {
    result := core.result
    previous := core.result.marginal
  }.elsewhen(io.initialize) {
    previous := io.prior
  }
  io.result := result
  io.state := previous
  io.outValid := RegNext(io.valid, false.B)
}
