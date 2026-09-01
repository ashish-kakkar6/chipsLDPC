package chipsldpc

import chisel3._

object TwoMinLogic {
  private final case class Candidate(value: UInt, losers: Seq[UInt])

  private def minimum(values: Seq[UInt]): UInt =
    if (values.size == 1) values.head
    else minimum(values.grouped(2).map {
      case Seq(a, b) => Mux(a <= b, a, b)
      case Seq(a)    => a
    }.toSeq)

  def apply(values: Seq[UInt]): (UInt, UInt) = {
    require(values.size >= 2)
    val bits = values.head.getWidth
    val paddedSize = 1 << BigInt(values.size - 1).bitLength
    val maximum = ((BigInt(1) << bits) - 1).U(bits.W)
    val leaves = values.map(Candidate(_, Seq.empty)) ++
      Seq.fill(paddedSize - values.size)(Candidate(maximum, Seq.empty))

    def tournament(level: Seq[Candidate]): Candidate =
      if (level.size == 1) level.head
      else tournament(level.grouped(2).map { pair =>
        val left = pair.head
        val right = pair(1)
        val leftWins = left.value <= right.value
        val history = left.losers.indices.map(i => Mux(leftWins, left.losers(i), right.losers(i)))
        Candidate(
          Mux(leftWins, left.value, right.value),
          history :+ Mux(leftWins, right.value, left.value),
        )
      }.toSeq)

    val winner = tournament(leaves)
    (winner.value, minimum(winner.losers))
  }
}

final class TwoMin(degree: Int, bits: Int) extends RawModule {
  require(degree >= 2 && bits > 0)
  val inputs = IO(Input(Vec(degree, UInt(bits.W))))
  val result = IO(Output(new MinPair(bits)))
  val (first, second) = TwoMinLogic(inputs.toSeq)
  result.first := first
  result.second := second
}
