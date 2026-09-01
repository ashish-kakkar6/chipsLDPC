package chipsldpc.graph

import org.scalatest.freespec.AnyFreeSpec

final class TannerNodeGraphsSpec extends AnyFreeSpec {
  private val steane = TannerGraph.fromRows(
    variableCount = 7,
    rowOnes = Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val nodes = TannerNodeGraphs.from(steane)

  "the node plan retains its canonical Tanner graph" in {
    assert(nodes.graph eq steane)
  }

  "the Steane checks retain canonical CNU ports" in {
    assert(nodes.checks == Vector(
      CheckNodeGraph(0, Vector(CheckEdgeRef(0, 3), CheckEdgeRef(1, 4),
        CheckEdgeRef(2, 5), CheckEdgeRef(3, 6))),
      CheckNodeGraph(1, Vector(CheckEdgeRef(4, 1), CheckEdgeRef(5, 2),
        CheckEdgeRef(6, 5), CheckEdgeRef(7, 6))),
      CheckNodeGraph(2, Vector(CheckEdgeRef(8, 0), CheckEdgeRef(9, 2),
        CheckEdgeRef(10, 4), CheckEdgeRef(11, 6))),
    ))
    assert(nodes.checks.map(_.degree) == Vector(4, 4, 4))
  }

  "the Steane variables retain canonical VNU ports" in {
    assert(nodes.variables == Vector(
      VariableNodeGraph(0, Vector(VariableEdgeRef(8, 2))),
      VariableNodeGraph(1, Vector(VariableEdgeRef(4, 1))),
      VariableNodeGraph(2, Vector(VariableEdgeRef(5, 1), VariableEdgeRef(9, 2))),
      VariableNodeGraph(3, Vector(VariableEdgeRef(0, 0))),
      VariableNodeGraph(4, Vector(VariableEdgeRef(1, 0), VariableEdgeRef(10, 2))),
      VariableNodeGraph(5, Vector(VariableEdgeRef(2, 0), VariableEdgeRef(6, 1))),
      VariableNodeGraph(6, Vector(VariableEdgeRef(3, 0), VariableEdgeRef(7, 1),
        VariableEdgeRef(11, 2))),
    ))
    assert(nodes.variables.map(_.degree) == Vector(1, 1, 2, 1, 2, 2, 3))
  }

  "both node views form a bijection with the global Steane edges" in {
    val fromChecks = nodes.checks.flatMap { node =>
      node.edges.map(ref => ref.edgeId -> TannerEdge(node.checkId, ref.variableId))
    }
    val fromVariables = nodes.variables.flatMap { node =>
      node.edges.map(ref => ref.edgeId -> TannerEdge(ref.checkId, node.variableId))
    }
    val edgeIds = steane.edges.indices.toVector

    assert(fromChecks.map(_._1) == edgeIds)
    assert(fromVariables.map(_._1).sorted == edgeIds)
    assert(fromChecks.forall { case (id, edge) => steane.edges(id) == edge })
    assert(fromVariables.forall { case (id, edge) => steane.edges(id) == edge })
  }

  "the Steane edges bind both local node ports" in {
    assert(nodes.connections == Vector(
      TannerConnection(0, 0, 0, 3, 0), TannerConnection(1, 0, 1, 4, 0),
      TannerConnection(2, 0, 2, 5, 0), TannerConnection(3, 0, 3, 6, 0),
      TannerConnection(4, 1, 0, 1, 0), TannerConnection(5, 1, 1, 2, 0),
      TannerConnection(6, 1, 2, 5, 1), TannerConnection(7, 1, 3, 6, 1),
      TannerConnection(8, 2, 0, 0, 0), TannerConnection(9, 2, 1, 2, 1),
      TannerConnection(10, 2, 2, 4, 1), TannerConnection(11, 2, 3, 6, 2),
    ))
  }
}
