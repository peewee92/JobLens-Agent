/** fetch decodes upstream compression; never forward its old wire metadata. */
export function forwardBackendResponse(response: Response): Response {
  const headers = new Headers(response.headers);
  for (const name of ["content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive", "upgrade", "proxy-authenticate", "proxy-authorization", "te", "trailer"]) headers.delete(name);
  return new Response([204, 205, 304].includes(response.status) ? null : response.body, {
    status: response.status, statusText: response.statusText, headers,
  });
}
