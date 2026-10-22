import { RuntimeClientError, RuntimeInvocationClient } from '../runtime/client.ts';
import type { RuntimeConfig, RuntimeTransport } from '../runtime/transport.ts';
import type { AgentRequest } from '../runtime/generated/contracts.ts';
import { validateOutput } from '../runtime/validation.ts';

export type ErrorDetails = { code: string; message: string };
const details = new WeakMap<Error, ErrorDetails>();
export function errorDetails(error: unknown): ErrorDetails {
  return error instanceof RuntimeClientError
    ? (details.get(error) ?? { code: error.runtimeCode ?? error.code, message: error.message })
    : { code: 'TRANSPORT_ERROR', message: 'TRANSPORT_ERROR' };
}

// Presentation side channel only: the unchanged client still validates, classifies
// and throws the original error. Per-exchange capture prevents concurrent mixing.
export function createPresentedClient(transport: RuntimeTransport, config: RuntimeConfig) {
  // Preserve construction-time public config validation as well.
  new RuntimeInvocationClient(transport, config);
  const exchange: RuntimeInvocationClient['exchange'] = async (envelope, options) => {
    let body: unknown;
    let requestId = '';
    const client = new RuntimeInvocationClient(
      {
        mode: transport.mode,
        async send(input, settings) {
          requestId =
            input.request?.request_id ??
            input.approval?.source_request_id ??
            input.clarification?.source_request_id ??
            input.message?.source_request_id ??
            '';
          const reply = await transport.send(input, settings);
          body = reply.body;
          return reply;
        },
      },
      config,
    );
    try {
      return await client.exchange(envelope, options);
    } catch (error) {
      if (error instanceof RuntimeClientError && error.code === 'RUNTIME_ERROR') {
        const result = validateOutput(structuredClone(body), requestId);
        if (result.error) details.set(error, { ...result.error });
      }
      throw error;
    }
  };
  return {
    exchange,
    async invoke(request: AgentRequest, options?: { signal?: AbortSignal }) {
      return (await this.exchange({ request }, options)).response!;
    },
  };
}

export function presentError(error: ErrorDetails, category?: string) {
  const identity = `${error.code} ${error.message}`;
  if (identity.includes('NO_TARGET_CONSISTENT_REPLANNING_INPUT'))
    return {
      title: '当前计划暂无可执行的调整依据',
      description: '系统尚未检测到与当前计划一致、且足以形成可执行修订方案的赛事变化。',
      action: '可继续使用当前计划，或等待新的赛事变化信息。',
    };
  if (identity.includes('INTENT_MODEL_FAILED'))
    return {
      title: '暂时无法理解本次请求',
      description: '模型未能稳定识别本次操作意图。',
      action: '请换一种更明确的表达后重新提交。',
    };
  if (
    /STALE[_ ]?(PLAN|REFERENCE)|(?:plan|reference).*stale|stale.*(?:plan|reference)/i.test(identity)
  )
    return {
      title: '当前计划已更新',
      description: '你选择的计划版本已经不是最新版本。',
      action: '请选择最新计划后重新操作。',
    };
  if (/APPROVAL_REPLAY|CONTINUATION_CONSUMED|CONSUMED_CONTINUATION/i.test(identity))
    return {
      title: '该审批已经处理',
      description: '同一审批请求不能重复提交。',
      action: '请查看当前计划状态。',
    };
  if (category === 'TRANSPORT_ERROR' || error.code === 'TRANSPORT_ERROR')
    return {
      title: '服务连接失败',
      description: '当前无法连接 Local Runtime。',
      action: '请确认本地服务是否正在运行。',
    };
  if (category === 'ABORTED' || error.code === 'ABORTED')
    return {
      title: '已停止等待回复',
      description: '请求已取消等待，业务操作的执行状态仍需确认。',
      action: '请检查当前工作流状态。取消等待不表示拒绝审批。',
    };
  if (category === 'CONTRACT_ERROR' || error.code === 'CONTRACT_ERROR')
    return {
      title: '请求未完成',
      description: '无法解析服务响应，本次内容未作为有效回复展示。',
      action: '请核对当前工作流状态。',
    };
  return {
    title: '请求未完成',
    description: '本次请求未能取得有效结果。',
    action: '请核对输入和当前工作流状态。',
  };
}

export function ErrorPresentation({ error, category }: { error: ErrorDetails; category?: string }) {
  const message = presentError(error, category);
  return (
    <>
      <strong>{message.title}</strong>
      <p>{message.description}</p>
      <p>{message.action}</p>
      <details>
        <summary>高级详情</summary>
        <p>{category}</p>
        <p>code：{error.code}</p>
        <p>message：{error.message}</p>
      </details>
    </>
  );
}
