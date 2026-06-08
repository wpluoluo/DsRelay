import { Badge, Button, Empty } from '../../components';
import type { Pool } from '../../types';
import { countLines } from '../../utils';
import { protocolText } from '../routes/routeFormat';

export function PoolList({
  pools,
  onOpenPool,
  onDeletePool,
  onMovePool,
}: {
  pools: Pool[];
  onOpenPool: (index: number | null) => void;
  onDeletePool: (index: number) => void;
  onMovePool: (index: number, direction: number) => void;
}) {
  return (
    <div className="section-stack">
      <div className="split-head">
        <div><h4>账号列表</h4></div>
        <Button tone="primary" onClick={() => onOpenPool(null)}>添加账号</Button>
      </div>
      {pools.length ? pools.map((pool, index) => (
        <div className="pool-card" key={`${pool.name}-${index}`}>
          <div>
            <strong>{pool.name || `账号 ${index + 1}`}</strong>
            <p>{(pool.urls || []).join(' · ') || '未配置地址'}</p>
            <div className="chip-row">
              <Badge tone={pool.enabled === false ? 'warn' : 'ok'}>{pool.enabled === false ? '停用' : '启用'}</Badge>
              <Badge>优先级 {pool.priority ?? 100}</Badge>
              <Badge>{protocolText(pool.route_policy?.text_upstream_protocol)}</Badge>
              <Badge>{countLines(pool.supported_models_text)} 模型</Badge>
              <Badge>{countLines(pool.model_aliases_text)} 映射</Badge>
            </div>
          </div>
          <div className="button-row">
            <Button onClick={() => onMovePool(index, -1)}>上移</Button>
            <Button onClick={() => onMovePool(index, 1)}>下移</Button>
            <Button onClick={() => onOpenPool(index)}>管理</Button>
            <Button tone="danger" onClick={() => onDeletePool(index)}>删除</Button>
          </div>
        </div>
      )) : <Empty>暂无账号。</Empty>}
    </div>
  );
}
