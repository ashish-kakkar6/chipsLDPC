package chipsldpc

import chisel3._
import chisel3.util.MuxLookup

object Arithmetic {
  def canonicalSign(sign: Bool, magnitude: UInt): Bool = sign && magnitude.orR
  def hardDecision(value: SInt): Bool = value < 0.S
  def hardDecision(value: SignMag): Bool = canonicalSign(value.sign, value.magnitude)

  def fromSignMag(message: SignMag, width: Int): SInt = {
    val magnitude = message.magnitude.pad(width).asSInt
    Mux(canonicalSign(message.sign, message.magnitude), 0.S(width.W) -% magnitude, magnitude)
  }

  def clipSigned(value: SInt, width: Int): SInt = {
    val inWidth = value.getWidth
    require(inWidth >= width)
    val maximum = (BigInt(1) << (width - 1)) - 1
    val minimum = -(BigInt(1) << (width - 1))
    Mux(
      value > maximum.S(inWidth.W),
      maximum.S(width.W),
      Mux(value < minimum.S(inWidth.W), minimum.S(width.W), value(width - 1, 0).asSInt),
    )
  }

  def toSignMag(value: SInt, bits: Int): (Bool, UInt) = {
    val width = value.getWidth
    val negative = value < 0.S
    val absolute = Mux(negative, (0.S(width.W) -% value).asUInt, value.asUInt)
    val maximum = (BigInt(1) << bits) - 1
    val magnitude = Mux(absolute > maximum.U(width.W), maximum.U(bits.W), absolute(bits - 1, 0))
    (negative && magnitude.orR, magnitude)
  }

  def sum(values: Seq[SInt], width: Int): SInt = {
    require(values.nonEmpty)
    def reduce(level: Seq[SInt]): SInt =
      if (level.size == 1) level.head
      else reduce(level.grouped(2).map {
        case Seq(a, b) => a +% b
        case Seq(a)    => a
      }.toSeq)
    reduce(values.map(_.pad(width)))
  }

  private def clipUnsigned(value: UInt, bits: Int): UInt = {
    val width = value.getWidth
    val maximum = (BigInt(1) << bits) - 1
    if (width <= bits) value.pad(bits)
    else Mux(value > maximum.U(width.W), maximum.U(bits.W), value(bits - 1, 0))
  }

  def scale(value: UInt, control: UInt, policy: CheckScale, bits: Int): UInt = policy match {
    case NoScale => value
    case VallsScale(a, b) => clipUnsigned((value >> a) +& (value >> b), bits)
    case RampScale(maxShift) =>
      MuxLookup(control, value)((0 to maxShift).map(i => i.U -> (value -% (value >> i))))
  }
}
