package chipsldpc.graph

final case class TannerEdge(check: Int, variable: Int)

/** Immutable, canonically numbered Tanner graph used only during elaboration. */
final class TannerGraph private (
    val checkCount: Int,
    val variableCount: Int,
    val edges: Vector[TannerEdge],
    val rowOnes: Vector[Vector[Int]],
    val colOnes: Vector[Vector[Int]],
    val checkEdges: Vector[Vector[Int]],
    val variableEdges: Vector[Vector[Int]],
) {
  val edgeCount: Int = edges.size
}

object TannerGraph {
  /** Build from H's nonzero columns per row; edge IDs are row-major. */
  def fromRows(variableCount: Int, rowOnes: Seq[Seq[Int]]): TannerGraph = {
    require(variableCount > 0, "variableCount must be positive")
    require(rowOnes.nonEmpty, "the graph must contain a check")

    val rows = rowOnes.zipWithIndex.map { case (row, check) =>
      val sorted = row.toVector.sorted
      require(sorted.nonEmpty, s"check $check is unused")
      require(sorted.forall(v => v >= 0 && v < variableCount),
        s"check $check contains a variable outside [0, $variableCount)")
      require(sorted.distinct.size == sorted.size, s"check $check contains duplicate variables")
      sorted
    }.toVector

    val edges = rows.zipWithIndex.flatMap { case (variables, check) =>
      variables.map(TannerEdge(check, _))
    }
    val offsets = rows.scanLeft(0)(_ + _.size)
    val checkEdges = rows.indices.map(i => (offsets(i) until offsets(i + 1)).toVector).toVector
    val columnChecks = Array.fill(variableCount)(Vector.newBuilder[Int])
    val columnEdges = Array.fill(variableCount)(Vector.newBuilder[Int])
    edges.zipWithIndex.foreach { case (edge, id) =>
      columnChecks(edge.variable) += edge.check
      columnEdges(edge.variable) += id
    }
    val cols = columnChecks.map(_.result()).toVector
    require(cols.forall(_.nonEmpty), "every variable must be incident to a check")

    new TannerGraph(
      rows.size,
      variableCount,
      edges,
      rows,
      cols,
      checkEdges,
      columnEdges.map(_.result()).toVector,
    )
  }
}
