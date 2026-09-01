package chipsldpc

import chisel3._

final class SignMag(bits: Int) extends Bundle {
  val sign      = Bool()
  val magnitude = UInt(bits.W)
}

final class MinPair(bits: Int) extends Bundle {
  val first  = UInt(bits.W)
  val second = UInt(bits.W)
}

final class EdgeMeta extends Bundle {
  val sign      = Bool()
  val useSecond = Bool()
}

final class CheckResult(config: CheckConfig) extends Bundle {
  val minima = new MinPair(config.q.magnitudeBits)
  val edges  = Vec(config.degree, new EdgeMeta)
}

final class CheckMessage(bits: Int) extends Bundle {
  val minima    = new MinPair(bits)
  val sign      = Bool()
  val useSecond = Bool()
}

final class VariableResult(config: VariableConfig) extends Bundle {
  val marginal  = SInt(config.q.accumulatorBits.W)
  val decision  = Bool()
  val extrinsic = Vec(config.degree, new SignMag(config.q.magnitudeBits))
}
