import {ProfileEditor} from "@/components/profile-editor";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchCurrentProfile,
  fetchCurrentSearchIntent,
} from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  try {
    const [profile, intent] = await Promise.all([
      fetchCurrentProfile(),
      fetchCurrentSearchIntent(),
    ]);

    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">Career Context</p>
          <h1>确认事实，再定义你想找什么</h1>
          <p className="lede">
            Profile 只保存你确认过的事实。每个技能必须引用 Evidence；SearchIntent 独立记录硬约束与软偏好。每次保存都会生成新版本，不覆盖历史。
          </p>
        </section>
        <ProfileEditor initialProfile={profile} initialIntent={intent} />
      </>
    );
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取职业画像时发生未知错误。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">Career Context</p>
          <h1>职业画像与求职意向</h1>
        </section>
        <ServiceError message={message} />
      </>
    );
  }
}
