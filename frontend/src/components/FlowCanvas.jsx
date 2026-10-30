import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Background, Controls, Handle, MiniMap, Position, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { createPortal } from 'react-dom';
import { Maximize2, Minimize2 } from 'lucide-react';
import { arrangeFiles } from '../lib/layout.js';

const EMPTY_EDGES = [];
const nodeTypes = { folder: FolderNode, module: ModuleNode };
const BADGE_CHARACTERS_PER_LINE = 32;
const BADGE_LIMITS = { routes: 3, classes: 3, functions: 3, imports: 3 };
const CLASSIFICATION_COLORS = {
  api_route: '#10b981',
  database_model: '#3b82f6',
  background_worker: '#f59e0b',
  service: '#8b5cf6',
  api: '#10b981',
  model: '#3b82f6',
  test: '#64748b',
  infrastructure: '#f59e0b',
  config: '#64748b',
  source: '#d5dfd9',
};

function estimatedTextLines(value, charactersPerLine = BADGE_CHARACTERS_PER_LINE) {
  return Math.max(1, Math.ceil(Array.from(String(value || '')).length / charactersPerLine));
}

function getBadgeGroups(metadata) {
  const allRoutes = (metadata?.routes || []).map((route) => (
    typeof route === 'string' ? route : `${route.method || 'GET'} ${route.path || ''}`
  ));
  const allClasses = (metadata?.classes || []).map((item) => (
    typeof item === 'string' ? item : (item.name || String(item))
  ));
  const allFunctions = (metadata?.functions || [])
    .filter((item) => {
      const name = typeof item === 'string' ? item : item.name;
      return name && (!name.startsWith('_') || name === '__init__');
    })
    .map((item) => typeof item === 'string' ? item : item.name);
  const allImports = (metadata?.internal_imports || []).map((item) => (
    typeof item === 'string' ? item : String(item)
  ));

  return {
    routes: allRoutes.slice(0, BADGE_LIMITS.routes),
    hiddenRoutes: allRoutes.slice(BADGE_LIMITS.routes),
    classes: allClasses.slice(0, BADGE_LIMITS.classes),
    hiddenClasses: allClasses.slice(BADGE_LIMITS.classes),
    functions: allFunctions.slice(0, BADGE_LIMITS.functions),
    hiddenFunctions: allFunctions.slice(BADGE_LIMITS.functions),
    imports: allImports.slice(0, BADGE_LIMITS.imports),
    hiddenImports: allImports.slice(BADGE_LIMITS.imports),
  };
}

function getVisibleBadgeLabels(metadata) {
  const groups = getBadgeGroups(metadata);
  return [
    ...groups.routes.map((text) => `GET ${text}`),
    ...(groups.hiddenRoutes.length ? [`+${groups.hiddenRoutes.length} more routes`] : []),
    ...groups.classes.map((text) => `class ${text}`),
    ...(groups.hiddenClasses.length ? [`+${groups.hiddenClasses.length} more classes`] : []),
    ...groups.functions.map((text) => `func ${text}`),
    ...(groups.hiddenFunctions.length ? [`+${groups.hiddenFunctions.length} more functions`] : []),
    ...groups.imports.map((text) => `import ${text}`),
    ...(groups.hiddenImports.length ? [`+${groups.hiddenImports.length} more imports`] : []),
  ];
}

function OverflowBadge({ items, category }) {
  const [isOpen, setIsOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState(null);
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const closeTimerRef = useRef(null);
  const count = items.length;
  const isLargeList = count > 5;

  useEffect(() => () => window.clearTimeout(closeTimerRef.current), []);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onOutsidePointerDown = (event) => {
      if (triggerRef.current?.contains(event.target) || popoverRef.current?.contains(event.target)) return;
      setIsOpen(false);
      setPinned(false);
    };
    document.addEventListener('pointerdown', onOutsidePointerDown, true);
    return () => document.removeEventListener('pointerdown', onOutsidePointerDown, true);
  }, [isOpen]);

  useLayoutEffect(() => {
    if (!isOpen || !triggerRef.current) return undefined;
    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(260, window.innerWidth - 16);
      const maxHeight = isLargeList ? 240 : 180;
      const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
      const below = rect.bottom + 6;
      const top = below + maxHeight <= window.innerHeight - 8
        ? below
        : Math.max(8, rect.top - maxHeight - 6);
      setPosition({ left, top, width, maxHeight });
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isOpen, isLargeList]);

  function openOnHover() {
    if (isLargeList || pinned) return;
    window.clearTimeout(closeTimerRef.current);
    setIsOpen(true);
  }

  function scheduleHoverClose() {
    if (pinned || isLargeList) return;
    closeTimerRef.current = window.setTimeout(() => setIsOpen(false), 140);
  }

  function togglePopover(event) {
    event.preventDefault();
    event.stopPropagation();
    window.clearTimeout(closeTimerRef.current);
    if (pinned) {
      setPinned(false);
      setIsOpen(false);
    } else {
      setPinned(true);
      setIsOpen(true);
    }
  }

  if (!count) return null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="module-overflow-badge nodrag nowheel"
        aria-expanded={isOpen}
        aria-haspopup={isLargeList ? 'dialog' : 'true'}
        onMouseEnter={openOnHover}
        onMouseLeave={scheduleHoverClose}
        onFocus={openOnHover}
        onBlur={scheduleHoverClose}
        onClick={togglePopover}
      >
        +{count} more {category}
      </button>
      {isOpen && position && createPortal(
        <div
          ref={popoverRef}
          className={`module-overflow-popover${isLargeList ? ' module-overflow-popover--scrollable' : ''}`}
          role={isLargeList ? 'dialog' : 'tooltip'}
          aria-label={`Additional ${category}`}
          style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.maxHeight }}
          onMouseEnter={() => window.clearTimeout(closeTimerRef.current)}
          onMouseLeave={scheduleHoverClose}
          onPointerDown={(event) => event.stopPropagation()}
          onWheel={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="module-overflow-popover__title">More {category}</div>
          <div className="module-overflow-popover__items">
            {items.map((item, index) => (
              <span className={`module-overflow-pill module-overflow-pill--${category}`} key={`${item}-${index}`}>
                {item}
              </span>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

function estimateModuleHeight(node, metadata) {
  const titleLines = estimatedTextLines(node.name || node.id, 27);
  const badgeLabels = getVisibleBadgeLabels(metadata);
  const badgeHeight = badgeLabels.reduce((total, label) => total + 21 + (estimatedTextLines(label) - 1) * 13, 0);
  const badgeGaps = Math.max(0, badgeLabels.length - 1) * 4;
  const classifications = metadata?.classifications || [];
  const warnings = metadata?.security_warnings || metadata?.heuristics || [];
  const extraBadges = classifications.length > 1 ? classifications.filter((role) => role !== metadata.classification).slice(0, 2).length : 0;
  const extraBadgeCount = extraBadges + (warnings.length > 0 ? 1 : 0);
  const extraBadgeHeight = extraBadgeCount ? 7 + extraBadgeCount * 21 + Math.max(0, extraBadgeCount - 1) * 4 : 0;

  // Account for the card padding, title/evidence, auxiliary labels, and wrapped pills.
  return Math.ceil(24 + titleLines * 16 + 3 + 14 + 9 + extraBadgeHeight + badgeHeight + badgeGaps);
}

function FolderNode({ data }) {
  return <div className="folder-node-label">{data.label}</div>;
}

function ModuleNode({ data }) {
  const { name, classification, evidenceLine, fileMeta, routes, classes, functions } = data;

  // Fallback or normalize routes, classes, functions from file metadata
  const resolvedRoutes = fileMeta?.routes || routes || [];
  const resolvedClasses = fileMeta?.classes || classes || [];
  const resolvedFunctions = fileMeta?.functions || functions || [];
  const badgeGroups = getBadgeGroups({
    routes: resolvedRoutes,
    classes: resolvedClasses,
    functions: resolvedFunctions,
    internal_imports: fileMeta?.internal_imports || [],
  });

  const warnings = fileMeta?.security_warnings || fileMeta?.heuristics || [];
  const fileType = fileMeta?.file_type || 'python';

  return (
    <div className={`custom-module-node custom-module-node--${fileType}`} style={{ width: '100%', boxSizing: 'border-box' }}>
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        style={{ width: 8, height: 8, background: '#64748b', border: '1px solid #0b1320' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        style={{ width: 8, height: 8, background: '#64748b', border: '1px solid #0b1320' }}
      />
      {/* Module Title */}
      <div className="module-node-title">
        {name}
      </div>
      
      {/* Classification & Line Evidence */}
      <div className="module-node-evidence">
        {classification} · L{evidenceLine}
      </div>

      {(fileMeta?.classifications?.length > 1 || warnings.length > 0) && (
        <div className="module-node-badges" style={{ marginBottom: 7 }}>
          {fileMeta?.classifications?.filter((role) => role !== classification).slice(0, 2).map((role) => (
            <span className="module-pill module-pill--class" key={role}>{role}</span>
          ))}
          {warnings.length > 0 && <span className="module-pill module-pill--security">⚠ {warnings.length} security {warnings.length === 1 ? 'flag' : 'flags'}</span>}
        </div>
      )}

      {/* Pill Badges Container */}
      <div className="module-node-badges">
        {/* API Route Badges */}
        {badgeGroups.routes.map((routeText, idx) => {
          return (
            <div
              key={`route-${idx}`}
              className="module-pill module-pill--route"
            >
              {routeText}
            </div>
          );
        })}
        <OverflowBadge items={badgeGroups.hiddenRoutes} category="routes" />

        {/* Class Badges (limit to top 2) */}
        {badgeGroups.classes.map((className, idx) => {
          return (
            <div
              key={`class-${idx}`}
              className="module-pill module-pill--class"
            >
              {className}
            </div>
          );
        })}
        <OverflowBadge items={badgeGroups.hiddenClasses} category="classes" />

        {/* Key Function Badges (limit to top 2, filtering out noisy dunders) */}
        {badgeGroups.functions.map((fName, idx) => {
            return (
              <div
                key={`func-${idx}`}
                className="module-pill module-pill--function"
              >
                {fName}
              </div>
            );
          })}
        <OverflowBadge items={badgeGroups.hiddenFunctions} category="functions" />

        {/* Internal import badges */}
        {badgeGroups.imports.map((importName, idx) => (
          <div className="module-import-pill" key={`import-${idx}`}>
            ↗ {importName}
          </div>
        ))}
        <OverflowBadge items={badgeGroups.hiddenImports} category="imports" />
      </div>
    </div>
  );
}

export default function FlowCanvas({ analysis, selectedFile, onSelectFile }) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reactFlowInstanceRef = useRef(null);
  const files = Object.entries(analysis.file_metadata || {});
  const graphNodes = analysis.module_nodes?.length
    ? analysis.module_nodes
    : files.map(([path]) => ({ id: path, file: path, name: path, type: 'module' }));
  const graphEdges = analysis.module_edges || EMPTY_EDGES;

  const nodes = useMemo(() => {
    const nodesWithHeights = graphNodes.map((node) => {
      const filePath = node.file || node.id;
      const metadata = analysis.file_metadata?.[filePath] || {};
      return { ...node, layoutHeight: estimateModuleHeight(node, metadata) };
    });

    return arrangeFiles(nodesWithHeights, graphEdges).map((layoutNode) => {
      if (layoutNode.type === 'folder') return layoutNode;
      const { id, x, y, ...node } = layoutNode;
      const filePath = node?.file || id;
      const fileMeta = analysis.file_metadata?.[filePath] || {};
      const isSelected = selectedFile === filePath;
      const classification = node?.classification || node?.type || 'source';
      const borderColor = CLASSIFICATION_COLORS[classification] || CLASSIFICATION_COLORS.source;

      return {
        id,
        position: { x, y },
        type: 'module',
        data: {
          name: node?.name || id,
          classification,
          evidenceLine: node?.evidence?.line || 1,
          file: filePath,
          fileMeta,
          file_type: fileMeta.file_type || node.file_type,
          classifications: fileMeta.classifications || node.classifications || [],
          security_warnings: fileMeta.security_warnings || fileMeta.heuristics || node.security_warnings || node.heuristics || [],
          heuristics: fileMeta.heuristics || node.heuristics || [],
          routes: fileMeta.routes || node.routes || [],
          classes: fileMeta.classes || node.classes || [],
          functions: fileMeta.functions || node.functions || []
        },
        style: {
          width: 220,
          border: isSelected ? '1px solid #34d399' : `1px solid ${borderColor}`,
          borderRadius: 12,
          padding: 12,
          background: fileMeta.file_type === 'infrastructure' || fileMeta.file_type === 'config' ? '#171d27' : '#111b29',
          fontSize: 12,
          boxShadow: isSelected ? '0 0 0 2px rgba(52, 211, 153, .12), 0 8px 24px rgba(0,0,0,.35)' : '0 8px 20px rgba(0,0,0,.25)',
          transition: 'border-color .18s ease, box-shadow .18s ease, background .18s ease',
        },
      };
    });
  }, [graphNodes, graphEdges, selectedFile, analysis.file_metadata]);

  const edges = useMemo(() => graphEdges
    .filter((edge) => nodes.some((node) => node.id === edge.source) && nodes.some((node) => node.id === edge.target))
    .map((edge, index) => {
      const isConnectedToSelected = selectedFile === edge.source || selectedFile === edge.target;
      return {
        id: `${edge.source}-${edge.target}-${index}`,
        source: edge.source,
        target: edge.target,
        label: `L${edge.line}`,
        animated: isConnectedToSelected,
        type: 'smoothstep',
        style: {
          stroke: isConnectedToSelected ? '#34d399' : '#62758b',
          strokeWidth: isConnectedToSelected ? 3 : 2,
        },
        labelStyle: {
          fill: '#cbd5e1',
          fontSize: 11,
          fontWeight: isConnectedToSelected ? '600' : '400',
        },
        labelBgStyle: { fill: '#101a27', fillOpacity: 0.96 },
      };
    }), [graphEdges, nodes, selectedFile]);

  useEffect(() => {
    if (!isFullscreen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isFullscreen]);

  useEffect(() => {
    let secondFrame;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        window.dispatchEvent(new Event('resize'));
        reactFlowInstanceRef.current?.fitView({ padding: 0.16, duration: 240 });
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [isFullscreen]);

  return (
    <section className={`flow-canvas${isFullscreen ? ' flow-canvas--fullscreen' : ''}`} aria-label="Codebase architecture graph">
      <div className="section-heading">
        <div>
          <p className="eyebrow">STRUCTURE</p>
          <h2>Module dependency graph</h2>
        </div>
        <span>{graphNodes.length} modules · {edges.length} dependencies</span>
      </div>
      {files.length ? (
        <div className={`react-flow-frame${isFullscreen ? ' react-flow-frame--fullscreen' : ''}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            className={isFullscreen ? 'react-flow-canvas--fullscreen' : undefined}
            style={{ width: '100%', height: '100%' }}
            fitView
            onInit={(instance) => { reactFlowInstanceRef.current = instance; }}
            onNodeClick={(_, node) => node.data.file && onSelectFile(node.data.file)}
          >
            <Background color="#26364a" gap={22} />
            <MiniMap pannable zoomable style={{ width: 50, height: 50 }} />
            <Controls />
            <div className="react-flow__panel react-flow__panel-top-right canvas-fullscreen-panel">
              <button
                type="button"
                className="canvas-fullscreen-toggle"
                onClick={() => setIsFullscreen((current) => !current)}
                aria-label={isFullscreen ? 'Exit full-screen canvas' : 'Open full-screen canvas'}
                title={isFullscreen ? 'Exit full screen (Esc)' : 'Full screen'}
              >
                {isFullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
              </button>
            </div>
          </ReactFlow>
        </div>
      ) : (
        <p className="empty-state">No Python files were found in this repository.</p>
      )}
    </section>
  );
}
