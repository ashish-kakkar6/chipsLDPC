package chipsldpc.graph

import org.scalatest.freespec.AnyFreeSpec

final class CodesSpec extends AnyFreeSpec {
  "the BB144 Hx fixture has the pinned sparse structure" in {
    val graph = Codes.bivariateBicycle144
    assert((graph.checkCount, graph.variableCount, graph.edgeCount) == (72, 144, 432))
    assert(graph.rowOnes.forall(_.size == 6))
    assert(graph.colOnes.forall(_.size == 3))
    assert(graph.rowOnes.head == Vector(1, 2, 18, 75, 78, 84))
  }
}
