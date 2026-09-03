package chipsldpc

/** Independent ascending-pivot GF(2) reference; free columns are zero. */
object Gf2Reference {
  final case class Solution(consistent: Boolean, bits: Vector[Int])

  def solve(rows: Seq[Int], rhs: Seq[Int], width: Int): Solution =
    solveBig(rows.map(BigInt(_)), rhs, width)

  def solveBig(rows: Seq[BigInt], rhs: Seq[Int], width: Int): Solution = {
    require(rows.size == rhs.size && width >= 0)
    val matrix = rows.zip(rhs).map { case (row, bit) =>
      row | (BigInt(bit) << width)
    }.toArray
    val pivots = Array.fill(width)(-1)
    var pivotRow = 0
    for (col <- 0 until width if pivotRow < matrix.length) {
      (pivotRow until matrix.length).find(matrix(_).testBit(col)).foreach { found =>
        val swap = matrix(pivotRow)
        matrix(pivotRow) = matrix(found)
        matrix(found) = swap
        for (row <- matrix.indices if row != pivotRow && matrix(row).testBit(col))
          matrix(row) ^= matrix(pivotRow)
        pivots(col) = pivotRow
        pivotRow += 1
      }
    }
    val mask = (BigInt(1) << width) - 1
    val consistent = !matrix.exists(row => (row & mask) == 0 && row.testBit(width))
    Solution(
      consistent,
      Vector.tabulate(width)(col =>
        if (pivots(col) >= 0 && matrix(pivots(col)).testBit(width)) 1 else 0
      ),
    )
  }
}
