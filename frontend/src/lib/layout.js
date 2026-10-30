import dagre from '@dagrejs/dagre';

const NODE_WIDTH = 205;
const NODE_HEIGHT = 64;
const GROUP_PADDING = 48;

function heightFor(node) {
  return Math.max(NODE_HEIGHT, Number(node.layoutHeight) || NODE_HEIGHT);
}

function folderFor(node) {
  const file = node.file || node.id;
  const separator = file.lastIndexOf('/');
  return separator < 0 ? '(root)' : file.slice(0, separator);
}

function createDagreGraph(direction = 'LR') {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  // Cards can vary considerably in height as routes, warnings, and symbol pills wrap.
  // Reserve generous spacing so unrelated files in the same rank stay visually distinct.
  graph.setGraph({ rankdir: direction, nodesep: 58, ranksep: 104, marginx: 20, marginy: 20 });
  return graph;
}

export function arrangeFiles(nodes, edges = []) {
  const folders = new Map();
  nodes.forEach((node) => {
    const folder = folderFor(node);
    if (!folders.has(folder)) folders.set(folder, []);
    folders.get(folder).push(node);
  });

  const groupLayouts = new Map();
  for (const [folder, members] of folders) {
    const local = createDagreGraph();
    members.forEach((node) => local.setNode(node.id, { width: NODE_WIDTH, height: heightFor(node) }));
    edges.forEach((edge) => {
      if (members.some((node) => node.id === edge.source) && members.some((node) => node.id === edge.target)) {
        local.setEdge(edge.source, edge.target);
      }
    });
    dagre.layout(local);
    const positions = members.map((node) => {
      const height = heightFor(node);
      return {
        ...node,
        x: local.node(node.id).x - NODE_WIDTH / 2,
        y: local.node(node.id).y - height / 2,
      };
    });
    const minX = Math.min(...positions.map((node) => node.x));
    const minY = Math.min(...positions.map((node) => node.y));
    const maxX = Math.max(...positions.map((node) => node.x + NODE_WIDTH));
    const maxY = Math.max(...positions.map((node) => node.y + heightFor(node)));
    const width = maxX - minX + GROUP_PADDING * 2;
    const height = maxY - minY + GROUP_PADDING * 2;
    groupLayouts.set(folder, {
      id: `folder:${folder}`,
      folder,
      width,
      height,
      positions: positions.map((node) => ({ ...node, x: node.x - minX + GROUP_PADDING, y: node.y - minY + GROUP_PADDING })),
    });
  }

  const groupGraph = createDagreGraph();
  groupLayouts.forEach((group, folder) => groupGraph.setNode(folder, { width: group.width, height: group.height }));
  const groupEdges = new Set();
  const folderByNode = new Map(nodes.map((node) => [node.id, folderFor(node)]));
  edges.forEach((edge) => {
    const source = folderByNode.get(edge.source);
    const target = folderByNode.get(edge.target);
    if (source !== target && groupLayouts.has(source) && groupLayouts.has(target)) {
      const key = `${source}\0${target}`;
      if (!groupEdges.has(key)) {
        groupEdges.add(key);
        groupGraph.setEdge(source, target);
      }
    }
  });
  dagre.layout(groupGraph);

  const result = [];
  groupLayouts.forEach((group, folder) => {
    const position = groupGraph.node(folder);
    const x = position.x - group.width / 2;
    const y = position.y - group.height / 2;
    result.push({
      id: group.id,
      type: 'folder',
      position: { x, y },
      data: { label: folder },
      draggable: false,
      selectable: false,
      style: { width: group.width, height: group.height, zIndex: -1 },
    });
    group.positions.forEach((node) => result.push({ ...node, x: x + node.x, y: y + node.y }));
  });
  return result;
}
