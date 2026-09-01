package chipsldpc.graph

import org.scalatest.freespec.AnyFreeSpec

final class TannerGraphSpec extends AnyFreeSpec {
  "fromRows derives both graph views and stable edge IDs" in {
    val graph = TannerGraph.fromRows(3, Seq(Seq(1, 0), Seq(2, 1)))

    assert(graph.checkCount == 2)
    assert(graph.variableCount == 3)
    assert(graph.edgeCount == 4)
    assert(graph.rowOnes == Vector(Vector(0, 1), Vector(1, 2)))
    assert(graph.colOnes == Vector(Vector(0), Vector(0, 1), Vector(1)))
    assert(graph.edges == Vector(
      TannerEdge(0, 0), TannerEdge(0, 1), TannerEdge(1, 1), TannerEdge(1, 2),
    ))
    assert(graph.checkEdges == Vector(Vector(0, 1), Vector(2, 3)))
    assert(graph.variableEdges == Vector(Vector(0), Vector(1, 2), Vector(3)))
  }

  "edge numbering is independent of each row's input order" in {
    val shuffled = TannerGraph.fromRows(3, Seq(Seq(2, 0, 1)))
    val sorted = TannerGraph.fromRows(3, Seq(Seq(0, 1, 2)))

    assert(shuffled.edges == sorted.edges)
    assert(shuffled.checkEdges == sorted.checkEdges)
    assert(shuffled.variableEdges == sorted.variableEdges)
  }

  "invalid dimensions and empty adjacency are rejected" in {
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(0, Seq(Seq.empty)))
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(1, Seq.empty))
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(1, Seq(Seq.empty)))
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(3, Seq(Seq(0, 2))))
  }

  "duplicate and out-of-range entries are rejected" in {
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(2, Seq(Seq(0, 0, 1))))
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(2, Seq(Seq(-1, 0, 1))))
    assertThrows[IllegalArgumentException](TannerGraph.fromRows(2, Seq(Seq(0, 1, 2))))
  }
}
