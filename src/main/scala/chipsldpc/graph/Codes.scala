package chipsldpc.graph

/** Small canonical parity-check graphs used by generators and tests. */
object Codes {
  val steane: TannerGraph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )

  /** Hx for the [[144,12,12]] code: A=X^3+Y+Y^2, B=Y^3+X+X^2. */
  val bivariateBicycle144: TannerGraph = {
    val ell = 12
    val m = 6
    val block = ell * m
    def at(x: Int, y: Int): Int = Math.floorMod(x, ell) * m + Math.floorMod(y, m)
    val rows = for (x <- 0 until ell; y <- 0 until m) yield Seq(
      at(x + 3, y), at(x, y + 1), at(x, y + 2),
      block + at(x, y + 3), block + at(x + 1, y), block + at(x + 2, y),
    )
    TannerGraph.fromRows(2 * block, rows)
  }
}
