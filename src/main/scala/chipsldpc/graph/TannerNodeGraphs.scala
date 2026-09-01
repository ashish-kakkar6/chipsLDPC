package chipsldpc.graph

final case class CheckEdgeRef private[chipsldpc] (edgeId: Int, variableId: Int)
final case class VariableEdgeRef private[chipsldpc] (edgeId: Int, checkId: Int)
final case class TannerConnection private[chipsldpc] (
    edgeId: Int, checkId: Int, checkPort: Int, variableId: Int, variablePort: Int,
)

/** One check's rooted, elaboration-only view of the Tanner graph. */
final case class CheckNodeGraph private[chipsldpc] (
    checkId: Int,
    edges: Vector[CheckEdgeRef],
) {
  val degree: Int = edges.size
}

/** One variable's rooted, elaboration-only view of the Tanner graph. */
final case class VariableNodeGraph private[chipsldpc] (
    variableId: Int,
    edges: Vector[VariableEdgeRef],
) {
  val degree: Int = edges.size
}

final case class TannerNodeGraphs private (
    graph: TannerGraph,
    checks: Vector[CheckNodeGraph],
    variables: Vector[VariableNodeGraph],
) {
  val connections: Vector[TannerConnection] = {
    val variablePorts = variables.flatMap { node =>
      node.edges.zipWithIndex.map { case (edge, port) => edge.edgeId -> port }
    }.toMap
    checks.flatMap { node =>
      node.edges.zipWithIndex.map { case (edge, port) =>
        TannerConnection(edge.edgeId, node.checkId, port, edge.variableId, variablePorts(edge.edgeId))
      }
    }
  }
  require(connections.map(_.edgeId) == graph.edges.indices)
}

object TannerNodeGraphs {
  /** Derive canonical CNU and VNU port views without renumbering global edges. */
  def from(graph: TannerGraph): TannerNodeGraphs = {
    val checks = Vector.tabulate(graph.checkCount) { checkId =>
      val edges = graph.checkEdges(checkId).map { edgeId =>
        CheckEdgeRef(edgeId, graph.edges(edgeId).variable)
      }
      CheckNodeGraph(checkId, edges)
    }
    val variables = Vector.tabulate(graph.variableCount) { variableId =>
      val edges = graph.variableEdges(variableId).map { edgeId =>
        VariableEdgeRef(edgeId, graph.edges(edgeId).check)
      }
      VariableNodeGraph(variableId, edges)
    }
    TannerNodeGraphs(graph, checks, variables)
  }
}
