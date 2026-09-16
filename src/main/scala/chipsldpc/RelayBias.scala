package chipsldpc

import chisel3._

/** Paper-compatible Relay-BP bias arithmetic from Fig. 3 and Table 2. */
private[chipsldpc] object RelayBias {
  /** Truncate every magnitude partial product before summing, then restore sign. */
  def reducedMultiply(value: SInt, beta: UInt, fractionalBits: Int): SInt = {
    require(fractionalBits >= 0)
    val valueBits = value.getWidth
    val workBits = valueBits + beta.getWidth + 1
    val widened = value.pad(valueBits + 1)
    val negative = widened < 0.S
    val magnitudeWide = Mux(
      negative,
      (0.S((valueBits + 1).W) -% widened).asUInt,
      widened.asUInt,
    )
    val magnitude = magnitudeWide(valueBits - 1, 0)
    val terms = (0 until valueBits).map { bit =>
      val scaled =
        if (bit >= fractionalBits) beta << (bit - fractionalBits)
        else beta >> (fractionalBits - bit)
      Mux(magnitude(bit), scaled.pad(workBits), 0.U(workBits.W)).asSInt
    }
    val positive = Arithmetic.sum(terms, workBits)
    Mux(negative, 0.S(workBits.W) -% positive, positive)
  }

  def apply(
      prior: SInt,
      previous: SInt,
      beta: UInt,
      q: Quantization,
      format: RelayFormat,
  ): SInt = {
    require(prior.getWidth == q.accumulatorBits)
    require(previous.getWidth == q.accumulatorBits)
    require(beta.getWidth == format.betaBits)
    val scaledPrior = reducedMultiply(prior, beta, format.fractionalBits)
    val scaledPrevious = reducedMultiply(previous, beta, format.fractionalBits)
    val workBits = scaledPrior.getWidth.max(scaledPrevious.getWidth).max(previous.getWidth) + 2
    val mixed = (scaledPrior.pad(workBits) +% previous.pad(workBits)) -%
      scaledPrevious.pad(workBits)
    Arithmetic.clipSigned(mixed, q.accumulatorBits)
  }
}
