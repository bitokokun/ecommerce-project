from django.db import migrations, models


def keep_one_default_address(apps, schema_editor):
    Address = apps.get_model("accounts", "Address")
    db = schema_editor.connection.alias
    user_ids = (
        Address.objects.using(db).filter(is_default=True)
        .values_list("user_id", flat=True).distinct()
    )
    for user_id in user_ids:
        ids = list(
            Address.objects.using(db).filter(user_id=user_id, is_default=True)
            .order_by("id").values_list("id", flat=True)
        )
        for duplicate_id in ids[1:]:
            Address.objects.using(db).filter(pk=duplicate_id).update(is_default=False)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.RunPython(keep_one_default_address, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="address",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_default=True), fields=("user",),
                name="one_default_address_per_user",
            ),
        ),
    ]
