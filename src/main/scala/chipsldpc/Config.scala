package chipsldpc

final case class Quantization(magnitudeBits: Int, accumulatorBits: Int) {
  require(magnitudeBits > 0)
  require(accumulatorBits >= magnitudeBits + 1)
}

object RelayDefaults {
  /** Legacy accumulator profile used by the existing vanilla benchmarks. */
  val q = Quantization(4, 7)
  val scale: CheckScale = RampScale(q.magnitudeBits)
  val priorScale = 2
  val memoryScale = 8

  /** Named FPGA-paper profile; kept separate so vanilla results do not drift. */
  val paperQ = Quantization(4, 5)
  val paperFormat = RelayFormat(betaBits = 4, fractionalBits = 3)
}

sealed trait CheckScale { def controlBits: Int = 1 }
case object NoScale extends CheckScale
final case class VallsScale(a: Int, b: Int) extends CheckScale {
  require(a >= 0 && b >= 0)
}
final case class RampScale(maxShift: Int) extends CheckScale {
  require(maxShift > 0)
  override val controlBits: Int = math.max(1, BigInt(maxShift).bitLength)
}

final case class CheckConfig(degree: Int, q: Quantization, scale: CheckScale = NoScale) {
  require(degree >= 2)
}

final case class VariableConfig(degree: Int, q: Quantization) {
  require(degree > 0)
  val workBits: Int = q.accumulatorBits + math.max(1, BigInt(degree).bitLength)
}

final case class RelayFormat(betaBits: Int, fractionalBits: Int) {
  require(fractionalBits >= 0 && betaBits > fractionalBits)
}
