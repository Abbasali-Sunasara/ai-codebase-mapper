const NODE_WIDTH = 220;
const NODE_HEIGHT = 64;
const GROUP_PADDING = 30;
let elkPromise;

function getElk() {
  if (!elkPromise) {
    elkPromise = Promise.all([
      import('elkjs/lib/elk-api.js'),
      import('elkjs/lib/elk-worker.min.js?url'),
    ]).then(([{ default: ELK }, { default: workerUrl }]) => new ELK({ workerUrl }));
  }
  return elkPromise;
}

function heightFor(node) {
  return Math.max(NODE_HEIGHT, Number(node.layoutHeight) || NODE_HEIGHT);
}

function folderFor(node) {
  const file = node.file || node.id;
  const separator = file.lastIndexOf('/');
  return separator < 0 ? '(root)' : file.slice(0, separator);
}

function createFolderNodes(positionedNodes) {
  const folders = new Map();
  positionedNodes.forEach((node) => {
    const folder = folderFor(node);
    if (!folders.has(folder)) folders.set(folder, []);
    folders.get(folder).push(node);
  });

  return [...folders].map(([folder, members]) => {
    const minX = Math.min(...members.map((node) => node.position.x));
    const minY = Math.min(...members.map((node) => node.position.y));
    const maxX = Math.max(...members.map((node) => node.position.x + NODE_WIDTH));
    const maxY = Math.max(...members.map((node) => node.position.y + heightFor(node)));
    const x = minX - GROUP_PADDING;
    const y = minY - GROUP_PADDING;
    return {
      id: `folder:${folder}`,
      type: 'folder',
      position: { x, y },
      data: { label: folder },
      draggable: false,
      selectable: false,
      connectable: false,
      style: {
        width: maxX - minX + GROUP_PADDING * 2,
        height: maxY - minY + GROUP_PADDING * 2,
        zIndex: -1,
      },
    };
  });
}

function fallbackPositions(nodes) {
  const columnGap = 120;
  const rowGap = 70;
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  let yByColumn = Array(columns).fill(0);
  return nodes.map((node, index) => {
    const column = index % columns;
    const height = heightFor(node);
    const position = { x: column * (NODE_WIDTH + columnGap), y: yByColumn[column] };
    yByColumn[column] += height + rowGap;
    return { ...node, position };
  });
}

/** Arrange every module in one ELK graph, then add folder backgrounds around results. */
export async function arrangeFiles(nodes, edges = []) {
  if (!nodes.length) return [];

  const nodeIds = new Set(nodes.map((node) => node.id));
  const elkGraph = {
    id: 'codebase',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.layered.spacing.nodeNodeBetweenLayers': '150',
      'elk.spacing.nodeNode': '80',
      'elk.alignment': 'CENTER',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'org.eclipse.elk.separateConnectedComponents': 'false',
      'elk.padding': '[top=30,left=30,bottom=30,right=30]',
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: NODE_WIDTH,
      height: heightFor(node),
    })),
    edges: edges
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map((edge, index) => ({
        id: `layout-edge-${index}`,
        sources: [edge.source],
        targets: [edge.target],
      })),
  };

  let positionedNodes;
  try {
    const elk = await getElk();
    const layout = await elk.layout(elkGraph);
    const positions = new Map((layout.children || []).map((node) => [node.id, node]));
    positionedNodes = nodes.map((node) => {
      const position = positions.get(node.id);
      return {
        ...node,
        position: { x: Number(position?.x) || 0, y: Number(position?.y) || 0 },
      };
    });
  } catch (error) {
    console.error('ELK layout failed; using grid fallback.', error);
    positionedNodes = fallbackPositions(nodes);
  }

  return [...createFolderNodes(positionedNodes), ...positionedNodes];
}
